# expertSystem/__init__.py
from .interface import infer_from_form



# to import this just do
#from expertSystem import infer_from_form

#ex = infer_from_form(request.form)  # returns ExpertOutput
# apply ex.filter_* to filter candidates
# add ex.class_bonus per dx to similarities
# show ex.reasons to the user
