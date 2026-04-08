from core.models import (
    ApprovalWorkflow,
    AuditLog,
    Document,
    DocumentView,
    Drillhole,
    Organisation,
    Process,
    Prospect,
    Tenement,
    UserProfile,
)

NUM_ORGANISATIONS = 3
NUM_USERS_PER_ORG = 4
NUM_PROCESSES_PER_ORG = 3
NUM_DRILLHOLES_PER_PROCESS = 4
NUM_PROSPECTS_PER_PROCESS = 2
NUM_TENEMENTS_PER_PROCESS = 2
NUM_DOCUMENTS_PER_PROCESS = 3
NUM_APPROVAL_WORKFLOWS = 6
NUM_AUDIT_LOGS = 20
NUM_DOCUMENT_VIEWS = 15

ORG_MODES = ["EXPLORATION", "MINING"]
PROCESS_MODES = ["PROJECT", "OPERATION"]
COMMODITIES = ["Gold", "Iron Ore", "Copper", "Lithium", "Nickel", "Zinc", "Coal"]
DOC_TYPES = ["JORC", "VALMIN", "TECHNICAL", "ENVIRONMENTAL", "COMPLIANCE", "INTERNAL"]
CONFIDENTIALITY_LEVELS = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
CLEARANCE_LEVELS = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
ROLES = ["GEOLOGIST", "MANAGER", "ANALYST", "ADMIN", "FIELD_TECH"]
DEPARTMENTS = ["Exploration", "Mining Ops", "Compliance", "Geology", "Environment"]
WORKFLOW_TYPES = ["JORC", "VALMIN"]
WORKFLOW_STATUSES = ["PENDING", "APPROVED", "REJECTED"]
AUDIT_ACTIONS = ["CREATE", "UPDATE", "DELETE", "VIEW"]
TAG_POOL = list(range(1, 20))

AU_LAT_RANGE = (-35.0, -18.0)
AU_LON_RANGE = (115.0, 150.0)


MODEL_TYPES = [
    DocumentView,
    AuditLog,
    ApprovalWorkflow,
    Document,
    Drillhole,
    Prospect,
    Tenement,
    Process,
    UserProfile,
    Organisation,
]
