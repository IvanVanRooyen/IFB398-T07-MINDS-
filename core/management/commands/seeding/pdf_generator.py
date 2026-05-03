from django.contrib.auth import get_user_model
from faker import Faker

fake = Faker()
User = get_user_model()


def jorc_content(org, process, commodity):
    title = f"JORC Resource Estimate - {process.name}"
    sections = [
        (
            "1. Heading 1",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "2. Heading 2",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "3. Heading 3",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "4. Heading 4",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "5. Heading 5",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
    ]
    return title, sections


def valmin_content(org, process, commodity):
    title = f"Independent Technical Valuation - {process.name} ({commodity})"
    sections = [
        (
            "1. Heading 1",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "2. Heading 2",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "3. Heading 3",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "4. Heading 4",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "5. Heading 5",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
    ]
    return title, sections


def technical_content(org, process, commodity):
    title = f"Pre-Feasibility Study - {process.name} {commodity} Project"
    sections = [
        (
            "1. Heading 1",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "2. Heading 2",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "3. Heading 3",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "4. Heading 4",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "5. Heading 5",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
    ]
    return title, sections


def environmental_content(org, process, commodity):
    title = f"Annual Environmental Monitoring Report - {process.name}"
    sections = [
        (
            "1. Heading 1",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "2. Heading 2",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "3. Heading 3",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "4. Heading 4",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "5. Heading 5",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
    ]
    return title, sections


def compliance_content(org, process, commodity):
    title = f"Regulatory Compliance Report - {process.name}, {org.name}"
    sections = [
        (
            "1. Heading 1",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "2. Heading 2",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "3. Heading 3",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "4. Heading 4",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "5. Heading 5",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
    ]
    return title, sections


def internal_content(org, process, commodity):
    title = f"Internal Technical Memorandum - {process.name}"
    sections = [
        (
            "1. Heading 1",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "2. Heading 2",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "3. Heading 3",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "4. Heading 4",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
        (
            "5. Heading 5",
            [
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed",
                "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            ],
        ),
    ]
    return title, sections
