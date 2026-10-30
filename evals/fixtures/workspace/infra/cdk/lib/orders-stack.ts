import { Stack, StackProps, aws_s3 as s3, aws_lambda as lambda } from "aws-cdk-lib";
import { Construct } from "constructs";

export class OrdersStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);
    new s3.Bucket(this, "Receipts", { publicReadAccess: true, blockPublicAccess: s3.BlockPublicAccess.BLOCK_ACLS });
    const fn = new lambda.Function(this, "Webhook", {
      runtime: lambda.Runtime.NODEJS_22_X,
      handler: "index.handler",
      code: lambda.Code.fromAsset("lambda"),
    });
    fn.addFunctionUrl({ authType: lambda.FunctionUrlAuthType.NONE });
  }
}
