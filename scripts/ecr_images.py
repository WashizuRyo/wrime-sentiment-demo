"""Push real images to Floci ECR and verify a full model layer download."""

import base64
import hashlib
import json
import os
import subprocess
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require_local_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname
        not in {
            "localhost",
            "127.0.0.1",
            "000000000000.dkr.ecr.ap-northeast-1.localhost",
        }
        or parsed.port != 4566
    ):
        raise RuntimeError("Refusing a registry URL outside local Floci")
    return parsed


def docker_command():
    # Keep the caller's Docker daemon, but never write registry credentials to
    # their real Docker config or credential helper.
    endpoint = subprocess.check_output(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        text=True,
    ).strip()
    config = ROOT / ".local/floci-docker"
    config.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.pop("DOCKER_CONTEXT", None)
    environment.pop("DOCKER_HOST", None)
    return ["docker", "--host", endpoint, "--config", str(config)], environment


def publish_images(ecr, repositories):
    command, environment = docker_command()
    authorization = ecr.get_authorization_token()["authorizationData"][0]
    require_local_url(authorization["proxyEndpoint"])
    # Floci 2.4 returns a hostname-style auth endpoint even in path mode.
    registry = "localhost:4566"
    username, password = (
        base64.b64decode(authorization["authorizationToken"]).decode().split(":", 1)
    )
    subprocess.run(
        [*command, "login", registry, "--username", username, "--password-stdin"],
        input=password,
        text=True,
        env=environment,
        check=True,
        capture_output=True,
    )
    records = []
    uris = {}
    for method, output in (
        ("lora", "LoRAImageRepository"),
        ("full", "FullImageRepository"),
    ):
        uri = repositories[output] + ":registry"
        require_local_url("http://" + uri.split("/", 1)[0])
        # The path-style URI includes account/region/repository. Repository names
        # are read back from ECR instead of relying on an ARN or a real AWS URL.
        matches = [
            item
            for item in ecr.describe_repositories()["repositories"]
            if item["repositoryUri"] == repositories[output]
        ]
        if len(matches) != 1:
            raise RuntimeError("Cannot identify the local ECR repository")
        repository = matches[0]["repositoryName"]
        subprocess.run(
            [*command, "tag", f"wrime-{method}:local", uri], env=environment, check=True
        )
        log_path = ROOT / f".local/ecr-{method}-push.log"
        print(f"Pushing real {method} image; progress: {log_path.name}", flush=True)
        with log_path.open("w") as log:
            subprocess.run(
                [*command, "push", uri],
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
        images = ecr.batch_get_image(
            repositoryName=repository, imageIds=[{"imageTag": "registry"}]
        )
        if images.get("failures") or len(images.get("images", [])) != 1:
            raise RuntimeError("Pushed image is not available through ECR")
        image = images["images"][0]
        manifest = json.loads(image["imageManifest"])
        if "layers" not in manifest:
            raise RuntimeError("Expected a single-platform Lambda image manifest")
        # This Dockerfile's last COPY contains the complete model/tokenizer.
        layer = manifest["layers"][-1]
        download = ecr.get_download_url_for_layer(
            repositoryName=repository, layerDigest=layer["digest"]
        )
        require_local_url(download["downloadUrl"])

        class HashingStream:
            def __init__(self, stream):
                self.stream = stream
                self.digest = hashlib.sha256()
                self.size = 0

            def read(self, size=-1):
                block = self.stream.read(size)
                self.digest.update(block)
                self.size += len(block)
                return block

        weights = ROOT / "models" / method / "model.safetensors"
        with weights.open("rb") as local:
            expected_weights = hashlib.file_digest(local, "sha256").hexdigest()
        model_verified = False
        print(
            f"Downloading and verifying the complete {method} model layer ({layer['size']} compressed bytes)",
            flush=True,
        )
        with urllib.request.urlopen(download["downloadUrl"], timeout=120) as stream:
            hashed = HashingStream(stream)
            with tarfile.open(fileobj=hashed, mode="r|gz") as archive:
                for member in archive:
                    if (
                        member.name.lstrip("./")
                        != f"opt/models/{method}/model.safetensors"
                    ):
                        continue
                    if member.size != weights.stat().st_size:
                        raise RuntimeError(
                            "Model size in ECR differs from the local artifact"
                        )
                    with archive.extractfile(member) as model_file:
                        actual_weights = hashlib.file_digest(
                            model_file, "sha256"
                        ).hexdigest()
                    if actual_weights != expected_weights:
                        raise RuntimeError(
                            "Downloaded model weights differ from the local artifact"
                        )
                    model_verified = True
            while hashed.read(1024 * 1024):
                pass
        size = hashed.size
        if (
            size != layer["size"]
            or "sha256:" + hashed.digest.hexdigest() != layer["digest"]
            or not model_verified
        ):
            raise RuntimeError(
                "Model layer download did not match its manifest/artifact"
            )
        # Remove only our registry tag, never the original wrime-*:local image.
        subprocess.run(
            [*command, "image", "rm", uri],
            env=environment,
            check=True,
            capture_output=True,
        )
        with (ROOT / f".local/ecr-{method}-pull.log").open("w") as log:
            subprocess.run(
                [*command, "pull", uri],
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
        inspected = json.loads(
            subprocess.check_output(
                [*command, "image", "inspect", uri], env=environment, text=True
            )
        )[0]
        expected_manifest = (
            uri.rsplit(":", 1)[0] + "@" + image["imageId"]["imageDigest"]
        )
        if expected_manifest not in inspected["RepoDigests"]:
            raise RuntimeError("Pulled image manifest differs from the pushed manifest")
        # Lambda must retrieve it again itself; no registry URI tag is left cached.
        subprocess.run(
            [*command, "image", "rm", uri],
            env=environment,
            check=True,
            capture_output=True,
        )
        missing = subprocess.run(
            [*command, "image", "inspect", uri],
            env=environment,
            capture_output=True,
            check=False,
        )
        if missing.returncode == 0:
            raise RuntimeError("Registry tag is still cached before Lambda execution")
        records.append(
            {
                "model": method,
                "image_uri": uri,
                "manifest_digest": image["imageId"]["imageDigest"],
                "layers": len(manifest["layers"]),
                "model_layer_bytes_downloaded": size,
                "model_layer_digest": layer["digest"],
                "sha256_verified": True,
                "model_file_sha256": expected_weights,
                "model_bytes_verified": weights.stat().st_size,
                "docker_push": "success",
                "docker_pull": "success",
                "image_manifest_verified": True,
                "registry_tag_removed_before_lambda": True,
            }
        )
        uris[output] = uri
    report = {
        "endpoint": "http://127.0.0.1:4566",
        "images": records,
        "scope": "Actual Docker push/pull plus streaming and SHA256 verification of each entire model layer. Other Docker layers may be cached.",
    }
    (ROOT / ".local/ecr-roundtrip.json").write_text(json.dumps(report, indent=2) + "\n")
    return uris


def verify_lambda_pulls():
    report_path = ROOT / ".local/ecr-roundtrip.json"
    report = json.loads(report_path.read_text())
    logs = subprocess.check_output(
        [
            "docker",
            "compose",
            "-f",
            str(ROOT / "compose.floci.yaml"),
            "logs",
            "--no-color",
        ],
        text=True,
    )
    for image in report["images"]:
        matches = [
            line.strip()
            for line in logs.splitlines()
            if f"Pulling image: {image['image_uri']}" in line
        ]
        if not matches:
            raise RuntimeError(
                "Cannot verify that Lambda pulled the image from the registry"
            )
        image["lambda_registry_pull_verified"] = True
        image["lambda_pull_log"] = matches[-1]
    report_path.write_text(json.dumps(report, indent=2) + "\n")
