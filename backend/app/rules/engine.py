"""apply_rules(form) -> form: the only entry point to the rules.

Runs normalize -> validators -> review_policy. Called by pipeline/service.py,
api/validate.py and api/export.py.

Owner: B
"""
