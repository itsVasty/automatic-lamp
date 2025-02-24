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
    assertions.Template.from_stack(stack).resource_count_is("AWS::SNS::Topic", 1)  # Assuming there's a dead-letter queue

    # Assert queue properties
    assertions.Template.from_stack(stack).has_resource_properties(
        "AWS::SNS::Topic",
        {
            "TopicName": "lms-events-topic"
        },
    )

    # Assert Lambda function properties
    assertions.Template.from_stack(stack).has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": "lms-events-sns-handler",
            "Handler": "lms_events.handlers.events_sns_handler.handler",
            "Runtime": "python3.11",
            "Timeout": 360,
            "TracingConfig": {"Mode": "Active"},
        },
    )
