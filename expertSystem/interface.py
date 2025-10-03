# a single function your teammates call


# expertSystem/interface.py
from .schema import Facts, ExpertOutput
from .normalize import facts_from_form
from .rules import infer

def infer_from_form(form_dict: dict) -> ExpertOutput:
    """Main entrypoint for the app. Called with request.form (dict-like)."""
    facts: Facts = facts_from_form(form_dict)
    return infer(facts)
