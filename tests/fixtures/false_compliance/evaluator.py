def evaluate_policy(document, rules):
    findings = []
    for rule in rules:
        if rule.applies(document):
            findings.append(rule.id)
    return findings
