Help me create an md that details a plan to implement the following.

Phase 1, training button:
Description:
Create a training button that will be able to load already classified .xlsx files, and then allow the user to update with new 5-tuples, and then rebuild the allowlist from this.

Once the classified file has been uploaded, the user has the option to add any new combinations not previously in allowlist to the allowlist

Design question: Since the allowlist is built from multiple sources, where should these updates go into?

The user should also have the option be able to upload a ndjson file at this stage, which will then show the results of the classifications with the new allowlist vs the old, with the most important metric being the TBC count. 

If the user is not satisfied with the results of the new allowlist, they can cancel the changes. 



A few important notes:
Make sure that the user is able to revert to the previous version of the allowlist.

An example .xlsx classified file has been provided: [Open Document](./20260528_-_CS_ticket_new_categorizations.xlsx)



When implementing this plan (actual coding portion, not the plan you will implement, so put this note in the plan md as well), please explain the steps and process, and output this into an md file, which will allow for me to review your design decisions and better catch any errors or bugs, as well as understand your code.


Phase 2, UI simplification:
Make UI simplified for non-technical user

The ultimate goal is to be able to minimize TBC. 
How do we know if the new allowlist is better than the old? Sometimes TBC count might increase with a new allowlist because more competing choices leads to less separation in scoring during the scoring phase. This is something to consider later on. Would this be an issue with updating the allowlist (in which case, a question to consider - should there be a baseline 'golden set' allowlist to compare to?), or is this an issue with the way the scoring/categorization works?

