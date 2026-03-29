EXECUTION_PLANS = {
    "auth": [
        {"action": "test_login"},
        {"action": "test_signup"},
        {"action": "test_password_reset"},
    ],
    "checkout": [
        {"action": "add_to_cart"},
        {"action": "checkout_flow"},
    ],
    "forms": [
        {"action": "test_forms"},
    ],
    "full_app": [
        {"action": "navigation"},
        {"action": "links"},
        {"action": "console_errors"},
    ],
}


def get_execution_plan(scan_task):
    return EXECUTION_PLANS.get(scan_task, EXECUTION_PLANS["full_app"])
