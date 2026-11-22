---
pr: pending
branch: fix-621/fuzz2
---
Request bodies now take booleans and numbers only as the JSON types the API description gives them. Before, the gateway quietly turned 0 into false, false into 0 and the text "5" into 5, so a wrong request still got a 200 (found by the api-fuzz job). A shared base model (onemind_core/jsonbody.py) checks this for all 23 request models with such fields, while still accepting 3.0 as the integer 3, which the earlier strict fix refused. A new test checks that every mounted request model uses it and that every such field on 21 routes refuses the wrong type with 422.
