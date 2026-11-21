import rules

from mcod.lib.rules import assigned_to_organization

# Editors (data providers) assigned to an institution; superusers bypass rules.
# Row-level limits (own institution, editable statuses) are enforced in AedReportAdmin.
rules.add_perm("aed", rules.always_allow)
rules.add_perm("aed.add_aedreport", assigned_to_organization)
rules.add_perm("aed.view_aedreport", assigned_to_organization)
rules.add_perm("aed.change_aedreport", assigned_to_organization)
rules.add_perm("aed.delete_aedreport", assigned_to_organization)
