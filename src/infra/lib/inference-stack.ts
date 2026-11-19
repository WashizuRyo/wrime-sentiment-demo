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

    const inferenceTimeout = cdk.Duration.seconds(120);

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
      // Keep both float32 models cached alongside the inference runtime.
      memorySize: 3008,
      timeout: inferenceTimeout,
      logGroup,
    });

    const api = fn.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.AWS_IAM,
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

      additionalBehaviors: {
        '/predict/*': {
          origin: origins.FunctionUrlOrigin.withOriginAccessControl(api, {
            readTimeout: inferenceTimeout,
          }),
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
        },
      },
    });
    distribution.applyRemovalPolicy(cdk.RemovalPolicy.DESTROY);

    const frontendUrl = `https://${distribution.distributionDomainName}`;

    new deployment.BucketDeployment(this, 'FrontendDeployment', {
      sources: [
        deployment.Source.asset(path.join(__dirname, '../../frontend/dist'), {
          exclude: ['config.json'],
        }),
        deployment.Source.jsonData('config.json', {
          apiBaseUrl: '',
          requirePayloadHash: true,
          methods: ['lora', 'full'],
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
    new cdk.CfnOutput(this, 'ApiUrl', { value: frontendUrl });
    new cdk.CfnOutput(this, 'FrontendBucketName', { value: bucket.bucketName });
    new cdk.CfnOutput(this, 'FunctionName', { value: fn.functionName });
    new cdk.CfnOutput(this, 'LogGroupName', { value: logGroup.logGroupName });
  }
}
