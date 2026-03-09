/*
 * Example YARA rules for trawler.
 * Add your own rules here or in separate .yar files.
 */

rule email_address {
    meta:
        description = "Detects email address patterns"
        severity = "low"
    strings:
        $email = /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/
    condition:
        $email
}

rule credential_pattern {
    meta:
        description = "Detects common credential dump patterns (user:pass or user,pass)"
        severity = "medium"
    strings:
        $colon_sep  = /[a-zA-Z0-9_.\-]{3,}:[^\s:]{6,}/
        $comma_pass = /password[,=:][^\s,]{4,}/i
    condition:
        any of them
}
