# Public API references checked before AWS implementation

Checked 2026-10-15 using public documentation only. No AWS API, console login or
account metadata was accessed. Installed versions and licenses are separately
recorded in dependency-licenses.json. The SDK is boto3/botocore 1.43.114; SAM
translator 1.115.0 is used only for offline checks.

- [PutItem](https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/client/put_item.html):
  conditional absence check with ExpressionAttributeNames, and conditional error semantics.
- [GetItem](https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/client/get_item.html):
  low-level typed attribute maps and `ConsistentRead=True`.
- [botocore Config](https://docs.aws.amazon.com/botocore/latest/reference/config.html):
  connect/read timeouts, standard retries with `total_max_attempts`, pool and endpoint configuration.
- [botocore Stubber](https://docs.aws.amazon.com/botocore/latest/reference/stubber.html):
  ordered offline SDK responses/errors with expected request parameters.
- [SAM API](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-resource-api.html),
  [endpoint configuration](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-property-api-endpointconfiguration.html),
  [route auth](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-property-function-apifunctionauth.html):
  explicit stage, method settings, regional endpoint shape and IAM event authorization.
- [DynamoDB TTL](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html):
  asynchronous deletion, requiring application read-time expiry checks.

The translator's installed source/signatures were inspected within this
workspace's virtual environment to exercise its offline Translator/Parser API.
Generated OpenAPI is checked rather than assuming the shorthand expanded as
intended. These references establish API usage, not live integration success.
