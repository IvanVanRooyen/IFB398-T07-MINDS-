import random

from django.contrib.auth import get_user_model
from faker import Faker

fake = Faker()
User = get_user_model()


def jorc_content(org, process, commodity):
    title = (
        f"Public Report: {commodity.capitalize()} Resource Estimate - {org.name} ({process.name})"
    )
    drill_type = "Diamond Core" if "Exploration" in process.name else "Reverse Circulation"

    sections = [
        (
            "1. Executive Summary",
            [
                f"This report outlines the mineral resource estimate for the {process.name} project.",
                f"The estimation was conducted in accordance with the JORC Code (2012 Edition) regarding {commodity}.",
            ],
        ),
        (
            "2. Geology and Mineralisation",
            [
                f"The deposit is characterized by {fake.word()}-hosted mineralisation within a {fake.word()} sequence.",
                f"Structural controls include {random.choice(['shear zones', 'faulting', 'stratigraphic pinch-outs'])}.",
            ],
        ),
        (
            "3. Sampling and Sub-sampling Techniques",
            [
                f"Sampling was primarily achieved via {drill_type} drilling.",
                "Samples were split using a riffle splitter to ensure representative sub-sampling for assaying.",
            ],
        ),
        (
            "4. Estimation and Reporting of Mineral Resources",
            [
                f"Ordinary Kriging was utilized for the {commodity} grade interpolation.",
                "Cut-off grades were determined based on current economic assumptions and metallurgical recovery rates.",
            ],
        ),
    ]
    return title, sections


def valmin_content(org, process, commodity):
    valuation_method = random.choice(["Income Approach (DCF)", "Market Approach", "Cost Approach"])
    title = f"Independent Technical Assessment and Valuation - {process.name} ({commodity})"

    sections = [
        (
            "1. Introduction and Scope",
            [
                f"The Practitioner has been commissioned by {org.name} to provide an independent valuation of the {process.name} asset.",
                "This report complies with the VALMIN Code (2015) for Public Reporting of Technical Assessments.",
            ],
        ),
        (
            "2. Project Tenure and Status",
            [
                f"The tenements are currently {fake.word()} and held 100% by the subsidiary.",
                f"Regulatory standing is confirmed as '{random.choice(['In Good Standing', 'Pending Renewal'])}'.",
            ],
        ),
        (
            "3. Technical Assessment",
            [
                f"Evaluation of the {commodity} extraction methodology indicates high technical feasibility.",
                f"The proposed {process.name} workflow aligns with industry best practices.",
            ],
        ),
        (
            "4. Valuation Methodology",
            [
                f"The primary valuation methodology employed is the {valuation_method}.",
                "Sensitivity analysis was performed on key value drivers including commodity price and OPEX.",
            ],
        ),
    ]
    return title, sections


def technical_content(org, process, commodity):
    """
    Generates content for a general Technical/Feasibility Report.
    """
    title = f"Technical Feasibility Study: {process.name} Operations"

    sections = [
        (
            "1. Project Infrastructure",
            [
                f"Current site infrastructure at {org.name} supports a processing capacity of {random.randint(1, 10)} Mtpa.",
                "Power requirements are met through a combination of grid and onsite LNG generation.",
            ],
        ),
        (
            "2. Metallurgical Testwork",
            [
                f"Recoveries for {commodity} are modeled at {random.uniform(85, 98):.1f}%.",
                f"Testwork was performed at {fake.company()} laboratories using representative composite samples.",
            ],
        ),
        (
            "3. Mine Design and Scheduling",
            [
                f"The mine plan utilizes a {random.choice(['top-down', 'block caving', 'open pit'])} sequence.",
                "Waste rock characterization indicates low potential for acid mine drainage.",
            ],
        ),
    ]
    return title, sections


def environmental_content(org, process, commodity):
    """
    Generates content for an Environmental Impact or Monitoring Report.
    """
    impact_level = random.choice(["Low", "Moderate", "Significant"])
    title = f"Annual Environmental Performance Report - {org.name}"

    sections = [
        (
            "1. Environmental Management Systems (EMS)",
            [
                f"Operations at {process.name} adhere to ISO 14001 standards.",
                "All environmental incidents during the period were recorded and remediated immediately.",
            ],
        ),
        (
            "2. Biodiversity and Land Rehabilitation",
            [
                f"Rehabilitation of the {fake.word()} stockpile area is {random.randint(40, 90)}% complete.",
                "Monitoring of local flora suggests no adverse impact from {commodity} processing.",
            ],
        ),
        (
            "3. Water and Tailings Management",
            [
                f"The Tailings Storage Facility (TSF) was inspected and rated as '{impact_level}' risk.",
                "Groundwater monitoring bores indicate levels remain within statutory limits.",
            ],
        ),
    ]
    return title, sections


def compliance_content(org, process, commodity):
    """
    Generates content for Regulatory and Compliance reports (e.g., Mining Act compliance).
    """
    title = f"Regulatory Compliance Audit - {process.name}"

    sections = [
        (
            "1. Statutory Obligations",
            [
                f"{org.name} has met all reporting obligations under the Mining Act for the {commodity} tenements.",
                "Rent and rates payments are up to date as of the reporting period.",
            ],
        ),
        (
            "2. Occupational Health and Safety (OHS)",
            [
                f"The Lost Time Injury Frequency Rate (LTIFR) for the {process.name} site is {random.uniform(0.5, 4.0):.2f}.",
                "Safety audits identified three minor non-conformances which have since been closed out.",
            ],
        ),
        (
            "3. Permit and License Register",
            [
                "Environmental Protection License (EPL) #4029 remains active.",
                f"Water extraction volumes for {commodity} leaching were within the {random.randint(100, 500)}ML allocation.",
            ],
        ),
    ]
    return title, sections


def internal_content(org, process, commodity):
    """
    Generates content for Internal Communication.
    """
    priority = random.choice(["URGENT", "Routine", "Confidential"])
    sender = fake.name()

    title = f"MEMO: [{priority}] Update on {process.name} - {commodity} Project"

    sections = [
        (
            "Internal Briefing",
            [
                f"To: Management Team, {org.name}",
                f"From: {sender}",
                f"Date: {fake.date()}",
            ],
        ),
        (
            "Subject: Operational Milestone",
            [
                f"We have successfully completed the phase one pilot for the {process.name} unit.",
                f"Initial assays for {commodity} are looking {random.choice(['promising', 'above budget', 'aligned with expectations'])}.",
            ],
        ),
        (
            "Action Items",
            [
                "Please review the attached data before our Friday stand-up.",
                "Procurement needs to be notified regarding long-lead items for the plant expansion.",
            ],
        ),
    ]
    return title, sections
