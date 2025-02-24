import aws_cdk as cdk
import aws_cdk.assertions as assertions

from python_cdk.grading_service_construct import GradingServiceConstruct
from python_cdk.lms_cdk_stack import LMSFullStack


# Test case for the GradingServiceStack
def test_grading_service_stack():
    # Create a new stack for testing
    app = cdk.App()
    # stack = GradingServiceConstruct(app, "TestGradingServiceStack")
    stack = LMSFullStack(app, "LmsTEST")

    # Assert that the queue is created
    assertions.Template.from_stack(stack).resource_count_is("AWS::SQS::Queue", 2)  # Assuming there's a dead-letter queue

    # Assert queue properties
    assertions.Template.from_stack(stack).has_resource_properties(
        "AWS::SQS::Queue",
        {
            "QueueName": "lms-grading-python-queue",
            "VisibilityTimeout": 370
        },
    )

    # Assert Lambda function properties
    assertions.Template.from_stack(stack).has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": "lms-grading-http-handler",
            "Handler": "lms_grading.handlers.grading_router_http_handler.handler",
            "Runtime": "python3.11",
            "Timeout": 30,
            "TracingConfig": {"Mode": "Active"},
        },
    )

    assertions.Template.from_stack(stack).has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": "lms-grading-sns-handler",
            "Handler": "lms_grading.handlers.grading_router_sns_handler.handler",
            "Runtime": "python3.11",
            "Timeout": 360,
            "TracingConfig": {"Mode": "Active"},
        },
    )

    # Assert API Gateway properties
    assertions.Template.from_stack(stack).has_resource_properties(
        "AWS::ApiGatewayV2::Api",
        {
            "Name": "lms-grading-api",
            "ProtocolType": "HTTP",
        },
    )

    assertions.Template.from_stack(stack).has_resource_properties(
        "AWS::ApiGatewayV2::Route",
        {
            "RouteKey": "POST /grade",
            "AuthorizationType": "NONE"
        },
    )

    # assertions.Template.from_stack(stack).has_resource_properties(
    #     "AWS::Lambda::Function",
    #     {
    #         "FunctionName": "lms-grading-python-ecr"
    #     },
    # )
