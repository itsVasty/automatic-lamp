import aws_cdk as core
import aws_cdk.assertions as assertions

from python_cdk.lms_cdk_stack import LMSFullStack


def test_lms_stack_created():
    app = core.App()
    stack = LMSFullStack(app, "LmsTEST")
    template = assertions.Template.from_stack(stack)

    # template.has_resource_properties("AWS::SQS::Queue", {
    #     ""
    #     "VisibilityTimeout": 300
    # })
