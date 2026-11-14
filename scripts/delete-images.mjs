import { spawnSync } from 'node:child_process';

const prefix = 'wrime-sentiment-demo-';
const aws = (...args) => spawnSync('aws', [...args, '--output', 'json'], {
  encoding: 'utf8',
  env: { ...process.env, AWS_PAGER: '' },
});
function json(...args) {
  const result = aws(...args);
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(result.stderr.trim() || 'AWS CLI failed');
  return JSON.parse(result.stdout);
}

try {
  // CDK can exit successfully when the user declines deletion. Never clean up
  // images while the inference stack still exists, or when its status is unknown.
  const stack = aws('cloudformation', 'describe-stacks', '--stack-name', 'WrimeInference');
  if (stack.error) throw stack.error;
  if (stack.status === 0 || !stack.stderr.includes('does not exist')) {
    throw new Error('Lambdaスタックの削除を確認できないため、イメージは削除しません。' + stack.stderr);
  }
  const bootstrap = json('cloudformation', 'describe-stacks', '--stack-name', 'CDKToolkit');
  const repository = bootstrap.Stacks[0].Outputs.find(
    output => output.OutputKey === 'ContainerAssetsRepositoryName',
  )?.OutputValue;
  if (!repository) throw new Error('CDK共用ECRが見つかりません。');

  // AWS CLI paginates list-images automatically. Delete by tag, never by digest:
  // another app may have its own tag on the very same image.
  const images = json('ecr', 'list-images', '--repository-name', repository).imageIds
    .filter(image => image.imageTag?.startsWith(prefix))
    .map(image => ({ imageTag: image.imageTag }));
  for (let i = 0; i < images.length; i += 100) {
    const result = json('ecr', 'batch-delete-image', '--repository-name', repository,
      '--image-ids', JSON.stringify(images.slice(i, i + 100)));
    const failures = (result.failures ?? []).filter(f => f.failureCode !== 'ImageNotFound');
    if (failures.length) throw new Error(JSON.stringify(failures));
  }
  console.log(`${repository}: このアプリのイメージタグを${images.length}件削除しました。`);
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
