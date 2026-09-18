import aws_cdk as cdk
from stacks.monitoring_stack import MonitoringStack

app = cdk.App()

MonitoringStack(
    app,
    "DevOpsAgentMonitoring",
    env=cdk.Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "eu-west-1",
    ),
    description="CloudWatch alarms + Lambda trigger for devops-agent-demo",
)

app.synth()
