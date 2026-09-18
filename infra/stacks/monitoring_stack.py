from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_logs as logs,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    aws_lambda as lambda_,
    aws_iam as iam,
)
from constructs import Construct
import os


class MonitoringStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        app_env = self.node.try_get_context("appEnv") or "production"
        log_group_name = f"/devops-agent-demo/{app_env}"
        github_repo = self.node.try_get_context("githubRepo") or "anubhuti-dazn/devops-agent-demo"
        github_token_secret = self.node.try_get_context("githubTokenSecret") or ""
        coralogix_endpoint = self.node.try_get_context("coralogixEndpoint") or ""
        coralogix_api_key_secret = self.node.try_get_context("coralogixApiKeySecret") or ""
        agent_space_id = self.node.try_get_context("agentSpaceId") or ""
        application_name = self.node.try_get_context("applicationName") or "devops-agent-demo"

        # ── 1. App log group ──────────────────────────────────────────────────
        app_log_group = logs.LogGroup(
            self,
            "AppLogGroup",
            log_group_name=log_group_name,
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── 2. Metric filter: count every ERROR log line ──────────────────────
        error_metric = logs.MetricFilter(
            self,
            "ErrorMetricFilter",
            log_group=app_log_group,
            metric_namespace="DevOpsAgentDemo",
            metric_name="ErrorCount",
            filter_pattern=logs.FilterPattern.string_value("$.level", "=", "ERROR"),
            metric_value="1",
            default_value=0,
            unit=cloudwatch.Unit.COUNT,
        )

        # ── 3. Alarm: any error in a 5-minute window fires immediately ─────────
        error_alarm = cloudwatch.Alarm(
            self,
            "ErrorAlarm",
            alarm_name=f"devops-agent-demo-{app_env}-errors",
            alarm_description="Fires when the application emits ERROR-level logs",
            metric=error_metric.metric(
                period=Duration.minutes(5),
                statistic="Sum",
            ),
            threshold=1,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        # ── 4. CI failure log group (written to by GitHub Actions) ────────────
        ci_log_group = logs.LogGroup(
            self,
            "CiLogGroup",
            log_group_name="/devops-agent-demo/ci",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=RemovalPolicy.RETAIN,
        )

        ci_error_metric = logs.MetricFilter(
            self,
            "CiErrorMetricFilter",
            log_group=ci_log_group,
            metric_namespace="DevOpsAgentDemo",
            metric_name="CiFailureCount",
            filter_pattern=logs.FilterPattern.string_value("$.event", "=", "ci_failure"),
            metric_value="1",
            default_value=0,
        )

        ci_alarm = cloudwatch.Alarm(
            self,
            "CiFailureAlarm",
            alarm_name=f"devops-agent-demo-{app_env}-ci-failures",
            alarm_description="Fires when GitHub Actions CI pipeline fails",
            metric=ci_error_metric.metric(
                period=Duration.minutes(5),
                statistic="Sum",
            ),
            threshold=1,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        # ── 5. SNS topic ──────────────────────────────────────────────────────
        alarm_topic = sns.Topic(
            self,
            "AlarmTopic",
            topic_name=f"devops-agent-demo-{app_env}-alarms",
            display_name="DevOps Agent Demo Alarms",
        )

        # ── 6. Lambda execution role ──────────────────────────────────────────
        lambda_role = iam.Role(
            self,
            "LambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        # Read recent error logs to include in the diagnosis prompt
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["logs:FilterLogEvents", "logs:GetLogEvents"],
                resources=[
                    app_log_group.log_group_arn,
                    ci_log_group.log_group_arn,
                ],
            )
        )

        # Call the AWS DevOps Agent service
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "devops-agent:CreateChat",
                    "devops-agent:SendMessage",
                ],
                resources=["*"],
            )
        )

        # Managed policies required by the DevOps Agent SDK (matching rca-analyser pattern)
        lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AIDevOpsAgentAccessPolicy")
        )

        # ── 7. Lambda function ────────────────────────────────────────────────
        trigger_fn = lambda_.Function(
            self,
            "TriggerDevOpsAgent",
            function_name=f"devops-agent-trigger-{app_env}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "..", "lambda", "trigger_devops_agent")
            ),
            role=lambda_role,
            timeout=Duration.seconds(120),
            memory_size=256,
            environment={
                # DevOps Agent
                "AGENT_SPACE_ID": agent_space_id,
                "APPLICATION_NAME": application_name,
                # Log sources
                "APP_LOG_GROUP": log_group_name,
                "CI_LOG_GROUP": "/devops-agent-demo/ci",
                "QUERY_WINDOW_HOURS": "1",
                # Coralogix (optional — falls back to CloudWatch if empty)
                "CORALOGIX_ENDPOINT": coralogix_endpoint,
                "CORALOGIX_API_KEY_SECRET_NAME": coralogix_api_key_secret,
                # GitHub issue reporting
                "GITHUB_REPO": github_repo,
                "GITHUB_TOKEN_SECRET_NAME": github_token_secret,
            },
            timeout=Duration.seconds(120),
        )

        # Allow Lambda to read GitHub token from Secrets Manager (optional)
        if github_token_secret:
            lambda_role.add_to_policy(
                iam.PolicyStatement(
                    actions=["secretsmanager:GetSecretValue"],
                    resources=[
                        f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:{github_token_secret}*"
                    ],
                )
            )

        # ── 8. Wire alarms → SNS → Lambda ─────────────────────────────────────
        sns_action = cw_actions.SnsAction(alarm_topic)
        error_alarm.add_alarm_action(sns_action)
        ci_alarm.add_alarm_action(sns_action)

        alarm_topic.add_subscription(subscriptions.LambdaSubscription(trigger_fn))

        # ── 9. CloudWatch Dashboard ───────────────────────────────────────────
        dashboard = cloudwatch.Dashboard(
            self,
            "MonitoringDashboard",
            dashboard_name=f"devops-agent-demo-{app_env}",
        )

        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Application Errors (5m)",
                left=[
                    error_metric.metric(period=Duration.minutes(5), statistic="Sum")
                ],
                width=12,
            ),
            cloudwatch.GraphWidget(
                title="CI Failures (5m)",
                left=[
                    ci_error_metric.metric(period=Duration.minutes(5), statistic="Sum")
                ],
                width=12,
            ),
            cloudwatch.AlarmStatusWidget(
                title="Alarm Status",
                alarms=[error_alarm, ci_alarm],
                width=24,
            ),
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        CfnOutput(self, "AppLogGroupName", value=app_log_group.log_group_name)
        CfnOutput(self, "CiLogGroupName", value=ci_log_group.log_group_name)
        CfnOutput(self, "AlarmTopicArn", value=alarm_topic.topic_arn)
        CfnOutput(self, "LambdaFunctionName", value=trigger_fn.function_name)
        CfnOutput(self, "DashboardUrl",
                  value=f"https://{self.region}.console.aws.amazon.com/cloudwatch/home#dashboards:name={dashboard.dashboard_name}")
