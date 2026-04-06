"""
EmailGenerator — Seeded, deterministic email generation.
All randomness via self.rng = random.Random(seed). No global random calls.
"""
import random
from typing import List, Tuple, Optional, Dict
from .models import (
    EmailPartial, EmailGroundTruth,
    EmailCategory, PriorityLevel, RouteAction,
)

# ---------------------------------------------------------------------------
# Template pool — 7 categories × 5 templates = 35 minimum
# Each template is a plain dict (not a Pydantic model).
# Keys: sender_name, sender_domain, subject, body, links, reply_to,
#       attachment_names, has_attachment, category, priority,
#       correct_route, is_phishing
# ---------------------------------------------------------------------------

_TEMPLATES: List[Dict] = [
    # ── URGENT (5) ──────────────────────────────────────────────────────────
    {
        "sender_name": "Ops Team", "sender_domain": "ops.internal.com",
        "subject": "Production database is down",
        "body": "Critical failure in the production database cluster. All services are affected. Immediate action required from on-call engineer.",
        "links": [], "reply_to": "ops@ops.internal.com",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.URGENT, "priority": PriorityLevel.CRITICAL,
        "correct_route": RouteAction.FLAG, "is_phishing": False,
    },
    {
        "sender_name": "Security Team", "sender_domain": "security.internal.com",
        "subject": "Unauthorized access detected on main server",
        "body": "We have detected unauthorized SSH access attempts on prod-server-01. Incident response required immediately.",
        "links": [], "reply_to": "security@security.internal.com",
        "attachment_names": ["incident_report.pdf"], "has_attachment": True,
        "category": EmailCategory.URGENT, "priority": PriorityLevel.CRITICAL,
        "correct_route": RouteAction.FLAG, "is_phishing": False,
    },
    {
        "sender_name": "Finance", "sender_domain": "finance.internal.com",
        "subject": "Invoice overdue — account suspension in 24h",
        "body": "Your vendor account will be suspended in 24 hours due to an overdue invoice. Please process payment immediately.",
        "links": ["https://finance.internal.com/invoices"], "reply_to": "finance@finance.internal.com",
        "attachment_names": ["invoice_Q4.pdf"], "has_attachment": True,
        "category": EmailCategory.URGENT, "priority": PriorityLevel.HIGH,
        "correct_route": RouteAction.FLAG, "is_phishing": False,
    },
    {
        "sender_name": "DevOps", "sender_domain": "devops.internal.com",
        "subject": "v1 API deprecation — 24 hours remaining",
        "body": "The v1 REST API will be shut down in 24 hours. All integrations must migrate to v2 before the deadline.",
        "links": ["https://docs.internal.com/api/v2"], "reply_to": "devops@devops.internal.com",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.URGENT, "priority": PriorityLevel.HIGH,
        "correct_route": RouteAction.FLAG, "is_phishing": False,
    },
    {
        "sender_name": "Backup System", "sender_domain": "backup.internal.com",
        "subject": "Data corruption detected in latest backup",
        "body": "Automated integrity check failed on backup-2024-01-15. Corruption detected in 3 of 12 shards. Manual review required.",
        "links": [], "reply_to": "backup@backup.internal.com",
        "attachment_names": ["backup_report.log"], "has_attachment": True,
        "category": EmailCategory.URGENT, "priority": PriorityLevel.CRITICAL,
        "correct_route": RouteAction.FLAG, "is_phishing": False,
    },

    # ── NORMAL (5) ──────────────────────────────────────────────────────────
    {
        "sender_name": "Alice Manager", "sender_domain": "company.com",
        "subject": "Quarterly review meeting — Thursday 2pm",
        "body": "Hi team, please find attached the agenda for our Q4 quarterly review. We will cover OKRs, budget, and roadmap.",
        "links": ["https://calendar.company.com/q4-review"], "reply_to": "alice@company.com",
        "attachment_names": ["q4_agenda.pdf"], "has_attachment": True,
        "category": EmailCategory.NORMAL, "priority": PriorityLevel.MEDIUM,
        "correct_route": RouteAction.ARCHIVE, "is_phishing": False,
    },
    {
        "sender_name": "Bob Dev", "sender_domain": "company.com",
        "subject": "PR #482 merged into main",
        "body": "The feature/auth-refactor branch has been merged into main. CI passed. Deployment scheduled for Friday.",
        "links": ["https://github.com/company/repo/pull/482"], "reply_to": "bob@company.com",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.NORMAL, "priority": PriorityLevel.LOW,
        "correct_route": RouteAction.ARCHIVE, "is_phishing": False,
    },
    {
        "sender_name": "HR Department", "sender_domain": "hr.company.com",
        "subject": "Expense report approved — $342.50",
        "body": "Your travel expense report for the November conference has been approved. Reimbursement will appear in your next paycheck.",
        "links": [], "reply_to": "hr@hr.company.com",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.NORMAL, "priority": PriorityLevel.LOW,
        "correct_route": RouteAction.ARCHIVE, "is_phishing": False,
    },
    {
        "sender_name": "IT Procurement", "sender_domain": "it.company.com",
        "subject": "Hardware request — approval needed",
        "body": "A hardware request for 2x MacBook Pro M3 has been submitted by the engineering team. Please approve or reject.",
        "links": ["https://it.company.com/requests/4821"], "reply_to": "it@it.company.com",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.NORMAL, "priority": PriorityLevel.MEDIUM,
        "correct_route": RouteAction.FLAG, "is_phishing": False,
    },
    {
        "sender_name": "People Team", "sender_domain": "company.com",
        "subject": "Welcome Sarah to the engineering team",
        "body": "Please join us in welcoming Sarah Chen to the backend engineering team. Sarah joins us from Stripe and will focus on payments infrastructure.",
        "links": [], "reply_to": "people@company.com",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.NORMAL, "priority": PriorityLevel.LOW,
        "correct_route": RouteAction.ARCHIVE, "is_phishing": False,
    },

    # ── SPAM (5) ─────────────────────────────────────────────────────────────
    {
        "sender_name": "Prize Center", "sender_domain": "win-prizes-now.biz",
        "subject": "You have been selected — claim your Tesla Model 3",
        "body": "Congratulations! You have been randomly selected to receive a free Tesla Model 3. Click the link to claim your prize before it expires.",
        "links": ["http://win-prizes-now.biz/claim?id=99182"], "reply_to": "noreply@win-prizes-now.biz",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.SPAM, "priority": PriorityLevel.LOW,
        "correct_route": RouteAction.DELETE, "is_phishing": False,
    },
    {
        "sender_name": "Pharma Direct", "sender_domain": "cheapmeds-online.net",
        "subject": "Cheap prescriptions — no doctor needed",
        "body": "Buy prescription medications at 90% off. No prescription required. Discreet shipping worldwide. Order now.",
        "links": ["http://cheapmeds-online.net/order"], "reply_to": "sales@cheapmeds-online.net",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.SPAM, "priority": PriorityLevel.LOW,
        "correct_route": RouteAction.DELETE, "is_phishing": False,
    },
    {
        "sender_name": "Marketing Pro", "sender_domain": "boost-revenue.co",
        "subject": "10x your revenue with our AI marketing tool",
        "body": "Our AI-powered marketing platform has helped 10,000 businesses grow. Try it free for 30 days. No credit card required.",
        "links": ["http://boost-revenue.co/trial"], "reply_to": "info@boost-revenue.co",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.SPAM, "priority": PriorityLevel.LOW,
        "correct_route": RouteAction.DELETE, "is_phishing": False,
    },
    {
        "sender_name": "Anonymous", "sender_domain": "darkmail.onion.to",
        "subject": "I have your passwords — pay now",
        "body": "I have recorded you visiting adult websites. Send 0.5 BTC to wallet 1A2B3C or I will send the recording to your contacts.",
        "links": [], "reply_to": "anon@darkmail.onion.to",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.SPAM, "priority": PriorityLevel.HIGH,
        "correct_route": RouteAction.DELETE, "is_phishing": False,
    },
    {
        "sender_name": "Dating Network", "sender_domain": "singles-near-you.com",
        "subject": "3 people near you want to meet tonight",
        "body": "You have 3 new matches in your area. Sign up free to see who they are. Limited time offer.",
        "links": ["http://singles-near-you.com/matches"], "reply_to": "noreply@singles-near-you.com",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.SPAM, "priority": PriorityLevel.LOW,
        "correct_route": RouteAction.DELETE, "is_phishing": False,
    },

    # ── PHISHING (5) ─────────────────────────────────────────────────────────
    {
        "sender_name": "DocuSign Security", "sender_domain": "docusign-secure.net",
        "subject": "Action required: Sign your document before it expires",
        "body": "A document has been sent to you for signature. It will expire in 24 hours. Click to review and sign.",
        "links": ["http://docusign-secure.net/sign?token=abc123"], "reply_to": "noreply@docusign-secure.net",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.PHISHING, "priority": PriorityLevel.CRITICAL,
        "correct_route": RouteAction.DELETE, "is_phishing": True,
    },
    {
        "sender_name": "AWS Billing", "sender_domain": "aws-billing-alert.com",
        "subject": "Your AWS account has been suspended",
        "body": "Unusual activity detected on your AWS account. Your account has been temporarily suspended. Verify your identity to restore access.",
        "links": ["http://aws-billing-alert.com/verify"], "reply_to": "billing@aws-billing-alert.com",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.PHISHING, "priority": PriorityLevel.CRITICAL,
        "correct_route": RouteAction.DELETE, "is_phishing": True,
    },
    {
        "sender_name": "IT Helpdesk", "sender_domain": "corp-it-helpdesk.cn",
        "subject": "URGENT: Reset your domain password now",
        "body": "Your corporate password expires today. You must reset it immediately to avoid losing access. Click the link below.",
        "links": ["http://corp-it-helpdesk.cn/reset-password"], "reply_to": "helpdesk@corp-it-helpdesk.cn",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.PHISHING, "priority": PriorityLevel.CRITICAL,
        "correct_route": RouteAction.DELETE, "is_phishing": True,
    },
    {
        "sender_name": "HR Payroll", "sender_domain": "hr-payroll-update.ru",
        "subject": "Update your direct deposit information",
        "body": "We are updating our payroll system. Please verify your bank account details to ensure your next paycheck is not delayed.",
        "links": ["http://hr-payroll-update.ru/verify-bank"], "reply_to": "payroll@hr-payroll-update.ru",
        "attachment_names": ["payroll_form.exe"], "has_attachment": True,
        "category": EmailCategory.PHISHING, "priority": PriorityLevel.HIGH,
        "correct_route": RouteAction.DELETE, "is_phishing": True,
    },
    {
        "sender_name": "Package Delivery", "sender_domain": "post-delivery-fee.bz",
        "subject": "Package delivery failed — pay $1 redelivery fee",
        "body": "We attempted to deliver your package but no one was home. Pay a $1 redelivery fee to reschedule.",
        "links": ["http://post-delivery-fee.bz/reschedule"], "reply_to": "delivery@post-delivery-fee.bz",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.PHISHING, "priority": PriorityLevel.MEDIUM,
        "correct_route": RouteAction.DELETE, "is_phishing": True,
    },

    # ── NEWSLETTER (5) ───────────────────────────────────────────────────────
    {
        "sender_name": "Python Weekly", "sender_domain": "pythonweekly.com",
        "subject": "Python Weekly #542 — Top articles this week",
        "body": "This week in Python: new PEP proposals, asyncio best practices, and a deep dive into the new match statement.",
        "links": ["https://pythonweekly.com/issue/542"], "reply_to": "editor@pythonweekly.com",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.NEWSLETTER, "priority": PriorityLevel.LOW,
        "correct_route": RouteAction.ARCHIVE, "is_phishing": False,
    },
    {
        "sender_name": "The Pragmatic Engineer", "sender_domain": "pragmaticengineer.com",
        "subject": "Inside Big Tech engineering culture",
        "body": "This week: how Google, Meta, and Amazon structure their engineering orgs, and what you can learn from each.",
        "links": ["https://pragmaticengineer.com/newsletter/big-tech-culture"], "reply_to": "gergely@pragmaticengineer.com",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.NEWSLETTER, "priority": PriorityLevel.LOW,
        "correct_route": RouteAction.ARCHIVE, "is_phishing": False,
    },
    {
        "sender_name": "TLDR Newsletter", "sender_domain": "tldr.tech",
        "subject": "TLDR 2024-01-15 — AI, Dev, and Science",
        "body": "Today's top stories: OpenAI releases new model, Rust 2024 edition announced, and a breakthrough in quantum computing.",
        "links": ["https://tldr.tech/2024-01-15"], "reply_to": "dan@tldr.tech",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.NEWSLETTER, "priority": PriorityLevel.LOW,
        "correct_route": RouteAction.ARCHIVE, "is_phishing": False,
    },
    {
        "sender_name": "Hacker News Digest", "sender_domain": "hndigest.com",
        "subject": "Top HN stories this week",
        "body": "Most upvoted stories: Ask HN: How do you manage burnout? | Show HN: I built a terminal emulator in Rust | Why I left FAANG.",
        "links": ["https://hndigest.com/weekly"], "reply_to": "digest@hndigest.com",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.NEWSLETTER, "priority": PriorityLevel.LOW,
        "correct_route": RouteAction.ARCHIVE, "is_phishing": False,
    },
    {
        "sender_name": "Morning Brew Tech", "sender_domain": "morningbrew.com",
        "subject": "Tech Brew: The AI arms race heats up",
        "body": "Good morning! Today we cover the latest moves in the AI space, semiconductor supply chain updates, and startup funding rounds.",
        "links": ["https://morningbrew.com/tech/2024-01-15"], "reply_to": "tech@morningbrew.com",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.NEWSLETTER, "priority": PriorityLevel.LOW,
        "correct_route": RouteAction.ARCHIVE, "is_phishing": False,
    },

    # ── INTERNAL (5) ─────────────────────────────────────────────────────────
    {
        "sender_name": "CTO Office", "sender_domain": "company.com",
        "subject": "Engineering all-hands — Friday 4pm",
        "body": "Reminder: Engineering all-hands this Friday at 4pm in the main conference room. Agenda: Q1 roadmap, team updates, open Q&A.",
        "links": ["https://calendar.company.com/all-hands"], "reply_to": "cto@company.com",
        "attachment_names": ["q1_roadmap.pdf"], "has_attachment": True,
        "category": EmailCategory.INTERNAL, "priority": PriorityLevel.MEDIUM,
        "correct_route": RouteAction.ARCHIVE, "is_phishing": False,
    },
    {
        "sender_name": "Platform Team", "sender_domain": "company.com",
        "subject": "Kubernetes cluster upgrade — maintenance window",
        "body": "We will be upgrading the k8s cluster from 1.27 to 1.29 this Saturday 2am-6am UTC. Expect brief service interruptions.",
        "links": [], "reply_to": "platform@company.com",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.INTERNAL, "priority": PriorityLevel.MEDIUM,
        "correct_route": RouteAction.ARCHIVE, "is_phishing": False,
    },
    {
        "sender_name": "Legal Team", "sender_domain": "company.com",
        "subject": "Updated employee handbook — action required",
        "body": "The employee handbook has been updated with new remote work policies. Please review and sign the acknowledgment form by Friday.",
        "links": ["https://hr.company.com/handbook-2024"], "reply_to": "legal@company.com",
        "attachment_names": ["handbook_2024.pdf"], "has_attachment": True,
        "category": EmailCategory.INTERNAL, "priority": PriorityLevel.MEDIUM,
        "correct_route": RouteAction.FLAG, "is_phishing": False,
    },
    {
        "sender_name": "Data Team", "sender_domain": "company.com",
        "subject": "New analytics dashboard is live",
        "body": "The new Grafana analytics dashboard is now live. You can access real-time metrics for your services at the link below.",
        "links": ["https://grafana.company.com/dashboards"], "reply_to": "data@company.com",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.INTERNAL, "priority": PriorityLevel.LOW,
        "correct_route": RouteAction.ARCHIVE, "is_phishing": False,
    },
    {
        "sender_name": "Office Manager", "sender_domain": "company.com",
        "subject": "Office kitchen renovation — temporary closure",
        "body": "The 3rd floor kitchen will be closed for renovation from Jan 20-27. Please use the 2nd floor kitchen during this period.",
        "links": [], "reply_to": "office@company.com",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.INTERNAL, "priority": PriorityLevel.LOW,
        "correct_route": RouteAction.ARCHIVE, "is_phishing": False,
    },

    # ── EXTERNAL (5) ─────────────────────────────────────────────────────────
    {
        "sender_name": "Acme Corp Sales", "sender_domain": "acmecorp.com",
        "subject": "Partnership proposal — Q1 2024",
        "body": "Hi, I am reaching out regarding a potential partnership between Acme Corp and your organization. I would love to schedule a 30-minute call.",
        "links": ["https://calendly.com/acme-sales"], "reply_to": "sales@acmecorp.com",
        "attachment_names": ["partnership_deck.pdf"], "has_attachment": True,
        "category": EmailCategory.EXTERNAL, "priority": PriorityLevel.LOW,
        "correct_route": RouteAction.ARCHIVE, "is_phishing": False,
    },
    {
        "sender_name": "GitHub", "sender_domain": "github.com",
        "subject": "Security alert: vulnerable dependency detected",
        "body": "Dependabot has detected a critical vulnerability in lodash 4.17.20 in your repository company/api-service. Update to 4.17.21.",
        "links": ["https://github.com/company/api-service/security/dependabot/1"], "reply_to": "noreply@github.com",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.EXTERNAL, "priority": PriorityLevel.HIGH,
        "correct_route": RouteAction.FLAG, "is_phishing": False,
    },
    {
        "sender_name": "Stripe", "sender_domain": "stripe.com",
        "subject": "Your monthly invoice — $2,340.00",
        "body": "Your Stripe invoice for January 2024 is ready. Total: $2,340.00. Payment will be charged to your card on file on Jan 20.",
        "links": ["https://dashboard.stripe.com/invoices/in_1234"], "reply_to": "receipts@stripe.com",
        "attachment_names": ["invoice_jan2024.pdf"], "has_attachment": True,
        "category": EmailCategory.EXTERNAL, "priority": PriorityLevel.MEDIUM,
        "correct_route": RouteAction.ARCHIVE, "is_phishing": False,
    },
    {
        "sender_name": "Conference Organizer", "sender_domain": "pycon.org",
        "subject": "Your PyCon 2024 talk has been accepted",
        "body": "Congratulations! Your talk proposal 'Async Python in Production' has been accepted for PyCon 2024. Please confirm your attendance.",
        "links": ["https://pycon.org/2024/speakers/confirm"], "reply_to": "speakers@pycon.org",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.EXTERNAL, "priority": PriorityLevel.MEDIUM,
        "correct_route": RouteAction.FLAG, "is_phishing": False,
    },
    {
        "sender_name": "Vendor Support", "sender_domain": "datadog.com",
        "subject": "Your support ticket #48291 has been resolved",
        "body": "Your support ticket regarding high cardinality metrics has been resolved. The fix has been deployed to your account.",
        "links": ["https://app.datadoghq.com/support/tickets/48291"], "reply_to": "support@datadog.com",
        "attachment_names": [], "has_attachment": False,
        "category": EmailCategory.EXTERNAL, "priority": PriorityLevel.LOW,
        "correct_route": RouteAction.ARCHIVE, "is_phishing": False,
    },
]


class EmailGenerator:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def generate(
        self,
        num_emails: int,
        ambiguity_level: float,
        has_phishing: bool,
        time_pressure: bool,
        max_steps: int,
    ) -> Tuple[List[EmailPartial], List[EmailGroundTruth]]:
        """
        Returns parallel lists (EmailPartial[], EmailGroundTruth[]).
        Deterministic: same inputs → same outputs every call.
        """
        # Separate phishing from non-phishing templates
        phishing_pool = [t for t in _TEMPLATES if t["is_phishing"]]
        normal_pool   = [t for t in _TEMPLATES if not t["is_phishing"]]

        selected: List[Dict] = []

        if has_phishing:
            # Guarantee at least 1 phishing email; up to ~25% of inbox
            num_phishing = max(1, self.rng.randint(1, max(1, num_emails // 4)))
            num_phishing = min(num_phishing, len(phishing_pool), num_emails)
            phishing_picks = self.rng.sample(phishing_pool, num_phishing)
            normal_picks   = [
                self.rng.choice(normal_pool)
                for _ in range(num_emails - num_phishing)
            ]
            selected = normal_picks + phishing_picks
        else:
            selected = [self.rng.choice(normal_pool) for _ in range(num_emails)]

        # Shuffle so phishing isn't always at the end
        self.rng.shuffle(selected)

        partials: List[EmailPartial]      = []
        ground_truths: List[EmailGroundTruth] = []

        for i, tmpl in enumerate(selected):
            email_id  = f"email_{i:03d}"
            timestamp = f"2024-01-15 {9 + i:02d}:00"

            # Apply ambiguity injection to non-phishing emails only
            if not tmpl["is_phishing"]:
                tmpl = self._inject_ambiguity(tmpl, ambiguity_level)

            deadline = self._assign_deadline(
                tmpl["category"], time_pressure, max_steps
            )

            partials.append(EmailPartial(
                email_id       = email_id,
                sender_name    = tmpl["sender_name"],
                sender_domain  = tmpl["sender_domain"],
                subject        = tmpl["subject"],
                preview        = tmpl["body"][:120],
                has_attachment = tmpl["has_attachment"],
                timestamp      = timestamp,
            ))

            ground_truths.append(EmailGroundTruth(
                email_id      = email_id,
                true_category = tmpl["category"],
                true_priority = tmpl["priority"],
                is_phishing   = tmpl["is_phishing"],
                deadline_step = deadline,
                correct_route = tmpl["correct_route"],
            ))

        return partials, ground_truths

    def _inject_ambiguity(self, template: Dict, level: float) -> Dict:
        """Returns a modified copy; never mutates the original."""
        t = dict(template)
        t["links"] = list(t["links"])  # shallow copy list

        if self.rng.random() < level:
            t["subject"] = "URGENT: " + t["subject"]

        if self.rng.random() < level * 0.5:
            t["links"].append("http://suspicious-link-injected.example.com/verify")

        return t

    def _assign_deadline(
        self,
        category: EmailCategory,
        time_pressure: bool,
        max_steps: int,
    ) -> Optional[int]:
        if category != EmailCategory.URGENT or not time_pressure:
            return None
        return self.rng.randint(5, max_steps - 5)
