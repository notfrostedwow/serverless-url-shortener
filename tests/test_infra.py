"""Static security contracts complement cfn-lint and SAM transformation."""

from pathlib import Path

import yaml


class Loader(yaml.SafeLoader):
    pass


def intrinsic(loader, tag, node):
    if isinstance(node, yaml.ScalarNode):
        return {tag: loader.construct_scalar(node)}
    if isinstance(node, yaml.SequenceNode):
        return {tag: loader.construct_sequence(node)}
    return {tag: loader.construct_mapping(node)}


Loader.add_multi_constructor("!", intrinsic)


def resources():
    loader = Loader(Path("infra/template.yaml").read_text(encoding="utf-8"))
    try:
        return loader.get_single_data()["Resources"]
    finally:
        loader.dispose()


def test_exact_table_and_log_group_permissions():
    template = resources()
    role = template["FunctionRole"]["Properties"]
    assert len(role["Policies"]) == 1
    table, logs = role["Policies"][0]["PolicyDocument"]["Statement"]
    assert table["Action"] == ["dynamodb:GetItem", "dynamodb:PutItem"]
    assert table["Resource"] == {"GetAtt": "Links.Arn"}
    assert logs["Action"] == ["logs:CreateLogStream", "logs:PutLogEvents"]
    assert logs["Resource"] == {
        "Sub": "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:"
        "log-group:/aws/lambda/${FunctionName}:log-stream:*"
    }
    assert template["Shortener"]["Properties"]["Role"] == {"GetAtt": "FunctionRole.Arn"}


def test_table_expiry_encryption_and_log_retention():
    template = resources()
    table = template["Links"]["Properties"]
    assert table["SSESpecification"] == {"SSEEnabled": True}
    assert table["TimeToLiveSpecification"] == {"AttributeName": "expires_at", "Enabled": True}
    assert table["BillingMode"] == "PAY_PER_REQUEST"
    assert template["FunctionLogs"]["Properties"]["RetentionInDays"] == 14
    assert template["Links"]["DeletionPolicy"] == "Retain"


def test_writes_require_iam_redirect_override_and_explicit_throttles():
    template = resources()
    api = template["RestApi"]["Properties"]
    assert api["StageName"] == "demo"
    assert "Auth" not in api
    settings = api["MethodSettings"][0]
    assert settings["ThrottlingRateLimit"] == 5
    assert settings["ThrottlingBurstLimit"] == 10
    assert settings["DataTraceEnabled"] is False
    assert settings["LoggingLevel"] == "OFF"
    events = template["Shortener"]["Properties"]["Events"]
    assert events["Create"]["Properties"]["Path"] == "/links"
    assert events["Create"]["Properties"]["Auth"] == {"Authorizer": "AWS_IAM"}
    assert "Auth" not in events["Redirect"]["Properties"]
    assert len(events) == 2


def test_ci_permissions_and_runtime_matrix():
    workflow = yaml.safe_load(Path(".github/workflows/checks.yml").read_text(encoding="utf-8"))
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["checks"]
    assert job["strategy"]["matrix"]["python-version"] == ["3.11", "3.12"]
    steps = job["steps"]
    assert steps[0]["with"]["persist-credentials"] is False
    for step in steps:
        assert "env" not in step
        if "uses" in step:
            assert len(step["uses"].split("@")[1]) == 40
    assert steps[-1]["run"] == "python tools/verify.py"
