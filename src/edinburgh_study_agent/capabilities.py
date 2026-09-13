"""Public capability boundaries, independent of a user's private access state."""
CAPABILITIES = {
    "implemented": [
        "Learn course/content discovery, verified downloads and document text reading",
        "Own EUCLID course marks and grades across loaded academic years; read-only, not an official transcript",
        "Supported MyEd/EUCLID student pages and Timetabler displayed-page reading",
        "Bounded official careers/events pages and MyCareerHub links",
        "Dated evidence, collections, tags, local tasks and draft plans",
        "Unified cached student agenda, linked local tasks and independent display timezone",
        "Ten-language service catalog, persistent preferences and per-call language overrides",
        "Portable MCP schemas, student tool profile and host configuration generator/merge installers",
        "Official DeepSeek MCP bridge integration tested with a registration fixture",
        "Local ICS import/export; one private profile and connection per person",
    ],
    "not_implemented": [
        "Shared hosted multi-user service or one public Work connection for all users",
        "Coursework submission, marking, grade changes, attendance or bulk student administration",
        "Job applications, event booking, enrolment changes or message sending",
        "Complete structured timetable sync, automatic refresh and remote calendar writes",
        "OCR, lecture-video transcription and all external/LTI providers",
    ],
    "unverified": [
        "Full Claude, WorkBuddy and DeepSeek model-turn acceptance; configuration/protocol/bridge tests are narrower",
        "Native-speaker review of every catalog translation and automatic translation of all source documents",
        "Teacher/staff-only Learn, EUCLID and administration pages",
        "Every feature of all 17 directory entries; actual coverage is per user and service",
        "Live campus operation on macOS/Linux; Windows is the campus acceptance host",
    ],
    "sharing": "Share the source/install package. Each person supplies their own campus login and private MCP/Work connection.",
}
