import { spawnSync } from 'node:child_process';

const imagePrefix = 'wrime-sentiment-demo-';
const filePrefix = 'wrime-sentiment-demo/';
const aws = (args, input) => spawnSync('aws', [...args, '--output', 'json'], {
  input,
  encoding: 'utf8',
  maxBuffer: 16 * 1024 * 1024,
  env: { ...process.env, AWS_PAGER: '' },
});
function json(args, input) {
  const result = aws(args, input);
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(result.stderr.trim() || 'AWS CLI failed');
  // S3 can return no body for successful list/delete operations (Quiet mode).
  const body = result.stdout.trim();
  return body ? JSON.parse(body) : {};
}

try {
  // CDK can exit successfully when the user declines deletion. Never clean up
  // assets while the inference stack still exists, or when its status is unknown.
  const stack = aws(['cloudformation', 'describe-stacks', '--stack-name', 'WrimeInference']);
  if (stack.error) throw stack.error;
  if (stack.status === 0 || !stack.stderr.includes('does not exist')) {
    throw new Error('Lambdaスタックの削除を確認できないため、イメージ・S3オブジェクトは削除しません。' + stack.stderr);
  }
  const bootstrap = json(['cloudformation', 'describe-stacks', '--stack-name', 'CDKToolkit']);
  const repository = bootstrap.Stacks[0].Outputs.find(
    output => ['ImageRepositoryName', 'ContainerAssetsRepositoryName'].includes(output.OutputKey),
  )?.OutputValue;
  const bucket = bootstrap.Stacks[0].Outputs.find(
    output => output.OutputKey === 'BucketName',
  )?.OutputValue;
  if (!repository || !bucket) throw new Error('CDK共用ECRまたはS3が見つかりません。');

  // AWS CLI paginates list-images automatically. Delete by tag, never by digest:
  // another app may have its own tag on the very same image.
  const images = json(['ecr', 'list-images', '--repository-name', repository]).imageIds
    .filter(image => image.imageTag?.startsWith(imagePrefix))
    .map(image => ({ imageTag: image.imageTag }));
  for (let i = 0; i < images.length; i += 100) {
    const result = json(['ecr', 'batch-delete-image', '--repository-name', repository,
      '--image-ids', 'file:///dev/stdin'], JSON.stringify(images.slice(i, i + 100)));
    const failures = (result.failures ?? []).filter(f => f.failureCode !== 'ImageNotFound');
    if (failures.length) throw new Error(JSON.stringify(failures));
  }
  console.log(`${repository}: このアプリのイメージタグを${images.length}件削除しました。`);

  // A versioned bucket retains data after an ordinary delete. Remove every
  // version and delete marker under this app's prefix, leaving the bucket intact.
  const files = json(['s3api', 'list-object-versions', '--bucket', bucket, '--prefix', filePrefix]);
  const objects = [...(files.Versions ?? []), ...(files.DeleteMarkers ?? [])]
    .filter(object => object.Key.startsWith(filePrefix))
    .map(object => ({ Key: object.Key, VersionId: object.VersionId }));
  for (let i = 0; i < objects.length; i += 1000) {
    const result = json(['s3api', 'delete-objects', '--bucket', bucket,
      '--delete', 'file:///dev/stdin'], JSON.stringify({ Objects: objects.slice(i, i + 1000), Quiet: true }));
    if (result.Errors?.length) throw new Error(JSON.stringify(result.Errors));
  }
  console.log(`${bucket}/${filePrefix}: オブジェクトのバージョン・削除マーカーを${objects.length}件削除しました。`);
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
