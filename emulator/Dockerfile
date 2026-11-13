FROM public.ecr.aws/amazonlinux/amazonlinux:2023-minimal
ARG TARGETARCH
ARG EMULATOR_VERSION=1.0.343
RUN case "$TARGETARCH" in arm64) echo aarch64 > /tmp/arch ;; amd64) echo x86_64 > /tmp/arch ;; *) exit 1 ;; esac \
    && curl -fsSL "https://downloads.aws.com/aws-emulator/packages/aws-emulator/LTS/aws-emulator-${EMULATOR_VERSION}-1-$(cat /tmp/arch).rpm" -o /tmp/emulator.rpm \
    && rpm -i /tmp/emulator.rpm && rm /tmp/emulator.rpm /tmp/arch \
    && mkdir -p /home/emulator && chown 1000 /home/emulator
USER 1000
ENV HOME=/home/emulator EMULATOR_TELEMETRY=off
EXPOSE 9297
ENTRYPOINT ["aws-emulator", "-b", "0.0.0.0", "--telemetry", "off"]
