import * as cdk from 'aws-cdk-lib/core';
import * as path from 'node:path';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as deployment from 'aws-cdk-lib/aws-s3-deployment';
import { Construct } from 'constructs';

export class InferenceStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const logGroup = new logs.LogGroup(this, 'Logs', {
      retention: logs.RetentionDays.ONE_DAY,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const fn = new lambda.DockerImageFunction(this, 'Function', {
      code: lambda.DockerImageCode.fromImageAsset(path.join(__dirname, '../..'), {
        file: 'backend/lambda/Dockerfile',
        ignoreMode: cdk.IgnoreMode.DOCKER,
      }),
      architecture: lambda.Architecture.ARM_64,
      memorySize: 3008,
      timeout: cdk.Duration.seconds(120),
      logGroup,
    });
    const bucket = new s3.Bucket(this, 'FrontendBucket', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });
    const distribution = new cloudfront.Distribution(this, 'Frontend', {
      defaultRootObject: 'index.html',
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(bucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
      },
    });
    distribution.applyRemovalPolicy(cdk.RemovalPolicy.DESTROY);
    const frontendUrl = `https://${distribution.distributionDomainName}`;
    const api = fn.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
      cors: {
        allowedOrigins: [frontendUrl],
        allowedMethods: [lambda.HttpMethod.POST],
        allowedHeaders: ['content-type'],
      },
    });
    new deployment.BucketDeployment(this, 'FrontendDeployment', {
      sources: [
        deployment.Source.asset(path.join(__dirname, '../../frontend/dist'), {
          exclude: ['config.json'],
        }),
        deployment.Source.jsonData('config.json', {
          apiBaseUrl: api.url,
          methods: ['lora'],
        }),
      ],
      destinationBucket: bucket,
      distribution,
      distributionPaths: ['/*'],
      logGroup: new logs.LogGroup(this, 'FrontendDeploymentLogs', {
        retention: logs.RetentionDays.ONE_DAY,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    });
    new cdk.CfnOutput(this, 'FrontendUrl', { value: frontendUrl });
    new cdk.CfnOutput(this, 'ApiUrl', { value: api.url });
    new cdk.CfnOutput(this, 'FrontendBucketName', { value: bucket.bucketName });
    new cdk.CfnOutput(this, 'FunctionName', { value: fn.functionName });
    new cdk.CfnOutput(this, 'LogGroupName', { value: logGroup.logGroupName });
  }
}
