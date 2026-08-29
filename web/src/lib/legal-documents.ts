export type LegalDocumentKind = "terms" | "privacy";

export interface LegalSection {
  id: string;
  title: string;
  paragraphs: string[];
  bullets?: string[];
}

export interface LegalDocument {
  slug: LegalDocumentKind;
  title: string;
  description: string;
  updatedLabel: string;
  updatedDate: string;
  contentsLabel: string;
  backToSignIn: string;
  companionLabel: string;
  companionTitle: string;
  companionHref: `/${LegalDocumentKind}`;
  sections: LegalSection[];
}

const UPDATED_DATE = "July 20, 2026";

const terms: LegalDocument = {
  slug: "terms",
  title: "Terms of Service",
  description:
    "These terms govern access to the Gateway console and its RPC routing, security, caching, and observability services.",
  updatedLabel: "Last updated",
  updatedDate: UPDATED_DATE,
  contentsLabel: "On this page",
  backToSignIn: "Back to sign in",
  companionLabel: "Also read",
  companionTitle: "Privacy Policy",
  companionHref: "/privacy",
  sections: [
    {
      id: "operator-and-scope",
      title: "1. Operator and scope",
      paragraphs: [
        '"Gateway" is the RPC gateway software and console made available through this deployment. "Operator" means the organization or person that provides this deployment to you, as identified in your account invitation, order, deployment notice, or other agreement. If you run Gateway yourself, you are the Operator for that deployment.',
        'These Terms apply to your access to and use of the hosted console, management APIs, and related services provided by the Operator (collectively, the "Service"). A signed agreement or order form controls if it conflicts with these Terms.',
      ],
    },
    {
      id: "acceptance-and-eligibility",
      title: "2. Acceptance and eligibility",
      paragraphs: [
        "By accessing or using the Service, you agree to these Terms and the Privacy Policy. If you use the Service for an organization, you represent that you have authority to bind that organization.",
        "You must be legally able to enter into this agreement and must not use the Service where doing so would violate applicable law, sanctions, export controls, or binding contractual restrictions.",
      ],
    },
    {
      id: "accounts-and-administration",
      title: "3. Accounts and administration",
      paragraphs: [
        "You must provide accurate account information, protect your password and active sessions, and promptly notify the Operator of suspected unauthorized access. You are responsible for activity performed through your account unless caused by the Operator's breach of these Terms.",
        "Workspace administrators may create, disable, archive, or delete accounts; assign roles; review login and operational information; and manage resources belonging to their workspace. Your access may therefore be controlled by the organization that invited you.",
      ],
    },
    {
      id: "service",
      title: "4. The Service",
      paragraphs: [
        "Gateway currently provides a control plane for accounts, applications, gateways, endpoint connection configuration, and provider synchronization. A public RPC traffic interface, routing, failover, usage reporting, caching, and gRPC are not part of the current release.",
        "The Operator may improve, replace, limit, or discontinue features. The Operator will use commercially reasonable efforts to avoid material disruption, but no blockchain network, upstream provider, internet route, or distributed system is continuously available or error-free.",
      ],
    },
    {
      id: "customer-configurations-and-traffic",
      title: "5. Your configurations",
      paragraphs: [
        'You retain your rights in the data, endpoint details, credentials, and other material you submit to the Service ("Customer Data"). You grant the Operator a limited right to process Customer Data only as needed to provide, secure, support, and improve the Service and to comply with law.',
        "You are responsible for ensuring that you have the rights and permissions needed to store endpoint and provider configuration in Gateway. Do not provide private keys, seed phrases, signing secrets, or other credentials that are not required for connection management.",
      ],
    },
    {
      id: "acceptable-use",
      title: "6. Acceptable use",
      paragraphs: [
        "You may not use the Service to violate law or third-party rights, compromise systems, evade access controls or rate limits, distribute malware, conduct unauthorized scanning or attacks, interfere with other users, or overload the Service or an upstream network.",
        "You may not resell or expose the Service in a way that exceeds your authorization, conceal abusive traffic, use stolen credentials, or use Gateway to access blockchain methods or data that you are not permitted to access.",
      ],
    },
    {
      id: "credentials-and-security",
      title: "7. Keys, credentials, and security",
      paragraphs: [
        "Application keys, bearer tokens, provider credentials, session cookies, and endpoint authentication secrets are sensitive. You must store and transmit them securely, rotate or revoke them when exposure is suspected, and restrict them to the least access necessary.",
        "The Service encrypts stored endpoint and provider credentials and may revoke sessions or suspend resources to protect the deployment. These controls reduce risk but do not replace your own security program, monitoring, backups, and incident response.",
      ],
    },
    {
      id: "third-parties-and-blockchains",
      title: "8. Third-party services and blockchain risks",
      paragraphs: [
        "The Service can connect to Google for sign-in and to blockchain nodes or infrastructure providers selected by you or the Operator. Those third parties operate under their own terms and privacy practices. The Operator is not responsible for their acts, omissions, pricing, availability, data accuracy, or security.",
        "Blockchain data can be delayed, reorganized, incomplete, inaccurate, or inconsistent across nodes. Networks can fork, halt, reject requests, change interfaces, or impose their own limits. You must independently validate data and transaction state before relying on it for financial, compliance, safety-critical, or irreversible decisions.",
      ],
    },
    {
      id: "fees",
      title: "9. Fees and limits",
      paragraphs: [
        "If your use is subject to fees, quotas, service levels, or usage commitments, they will be described in an order form, plan, deployment notice, or separate agreement. You are responsible for charges incurred through credentials and resources under your control, except to the extent caused by the Operator's breach.",
        "The Operator may enforce technical or contractual limits, including request rate, concurrency, storage, retention, chain, network, method, or upstream limits.",
      ],
    },
    {
      id: "intellectual-property",
      title: "10. Intellectual property and feedback",
      paragraphs: [
        "These Terms do not transfer ownership of Gateway, the Service, documentation, trademarks, or Operator content. Any open-source components remain governed by their applicable licenses.",
        "If you provide suggestions or feedback, the Operator may use them without restriction or payment, but will not identify you publicly as the source without permission.",
      ],
    },
    {
      id: "suspension-and-termination",
      title: "11. Suspension and termination",
      paragraphs: [
        "You may stop using the Service at any time. The Operator or your workspace administrator may suspend or terminate access when required by law, when you breach these Terms, when your use creates security or operational risk, when fees remain unpaid, or when the deployment is discontinued.",
        "Upon termination, your right to use the Service ends. Provisions that by their nature should survive—including ownership, payment obligations, disclaimers, liability limits, and dispute terms—will survive. Data handling after termination is described in the Privacy Policy and any applicable agreement.",
      ],
    },
    {
      id: "disclaimers",
      title: "12. Disclaimers",
      paragraphs: [
        'To the maximum extent permitted by law, the Service is provided "as is" and "as available." The Operator disclaims implied warranties of merchantability, fitness for a particular purpose, non-infringement, and any warranty that the Service or blockchain data will be uninterrupted, secure, accurate, complete, or free of harmful components.',
        "The Service is infrastructure software, not financial, investment, legal, tax, custody, brokerage, or compliance advice. You remain responsible for decisions and systems that rely on the Service.",
      ],
    },
    {
      id: "liability",
      title: "13. Limitation of liability",
      paragraphs: [
        "To the maximum extent permitted by law, neither the Operator nor its suppliers will be liable for indirect, incidental, special, consequential, exemplary, or punitive damages, or for lost profits, revenue, data, goodwill, digital assets, or business interruption arising from the Service.",
        "Unless a separate agreement states otherwise, the aggregate liability of the Operator for claims relating to the Service will not exceed the greater of the amount you paid for the Service during the 12 months before the event giving rise to the claim or USD 100. Some jurisdictions do not allow certain exclusions, so these limits apply only to the extent permitted by law.",
      ],
    },
    {
      id: "general",
      title: "14. General terms and contact",
      paragraphs: [
        "You will comply with applicable law and indemnify the Operator against third-party claims arising from your unlawful use, your Customer Data, or your breach of these Terms, to the extent permitted by law. You may not assign these Terms without the Operator's consent; the Operator may assign them as part of a merger, reorganization, or transfer of the Service.",
        "The governing law and dispute forum are those stated in your order form, deployment notice, or other agreement. If none is stated, mandatory law and the rules applicable where the Operator is established will determine them. If part of these Terms is unenforceable, the remainder stays effective. A failure to enforce a provision is not a waiver.",
        "The Operator may update these Terms to reflect service, legal, or security changes. The updated date will be shown above, and material changes may be announced through the Service or your workspace administrator. Questions or legal notices should be sent to the Operator identified by your organization or deployment administrator.",
      ],
    },
  ],
};

const privacy: LegalDocument = {
  slug: "privacy",
  title: "Privacy Policy",
  description:
    "This policy explains how information is processed when you use the Gateway console and RPC infrastructure.",
  updatedLabel: "Last updated",
  updatedDate: UPDATED_DATE,
  contentsLabel: "On this page",
  backToSignIn: "Back to sign in",
  companionLabel: "Also read",
  companionTitle: "Terms of Service",
  companionHref: "/terms",
  sections: [
    {
      id: "scope-and-roles",
      title: "1. Scope and responsible party",
      paragraphs: [
        'This Privacy Policy applies to the Gateway deployment you access. The organization or person providing that deployment (the "Operator") is responsible for its privacy practices. The Operator may be identified in your invitation, order, deployment notice, or by your workspace administrator.',
        "Gateway can be self-hosted. In a self-hosted deployment, the organization running it determines what information is collected, where it is stored, how long it is retained, and which infrastructure providers can process it. This policy describes the standard product behavior; deployment-specific notices or agreements may provide additional details and control if they conflict.",
      ],
    },
    {
      id: "information-collected",
      title: "2. Information processed",
      paragraphs: [
        "Depending on how the deployment is configured and how you use it, Gateway may process the following categories of information:",
      ],
      bullets: [
        "Account information, such as email address, role, account status, and—when supplied by Google—name, profile image, Google account identifier, and verified-email status.",
        "Authentication and security information, such as password hashes (not plaintext passwords), session token hashes, login time, IP address, user agent, OAuth state, security events, and rate-limit signals.",
        "Workspace configuration, such as applications, application keys, gateways, chains, networks, endpoint details, provider identifiers, and encrypted endpoint authentication secrets.",
        "Operational records, such as service logs, configuration changes, provider synchronization failures, and diagnostic information generated while operating and securing the Service.",
      ],
    },
    {
      id: "sources",
      title: "3. Sources of information",
      paragraphs: [
        "Information comes from you and your workspace administrators, from the browser or client connecting to the Service, from Google when you choose Google sign-in, and from infrastructure providers you configure for discovery or connection management.",
        "The Service does not require advertising trackers. A particular Operator may add monitoring or analytics outside the standard product; if so, that Operator is responsible for disclosing those tools.",
      ],
    },
    {
      id: "uses",
      title: "4. How information is used",
      paragraphs: ["The Operator may process information to:"],
      bullets: [
        "authenticate users, maintain sessions, administer accounts, and provide workspace permissions;",
        "manage applications, gateways, endpoints, and provider synchronization;",
        "protect credentials, detect abuse, investigate incidents, troubleshoot errors, and maintain reliability;",
        "support users, enforce agreements, comply with legal obligations, and establish or defend legal claims; and",
        "analyze aggregate performance and improve the Service without using RPC payloads for advertising profiles.",
      ],
    },
    {
      id: "cookies",
      title: "5. Cookies and local storage",
      paragraphs: [
        "Gateway uses an essential, HTTP-only session cookie to keep you signed in and a short-lived OAuth state cookie to protect the Google sign-in flow. These cookies are used for authentication and security, not cross-site advertising.",
        "Your browser may also retain ordinary technical data needed by the web application. Blocking essential cookies can prevent sign-in or other authenticated features from working.",
      ],
    },
    {
      id: "disclosures",
      title: "6. Disclosures and third parties",
      paragraphs: [
        "The Operator may disclose information to workspace administrators and authorized personnel; hosting, database, cache, network, security, support, and other processors used to run the deployment; Google when you use Google sign-in; and the upstream blockchain providers selected for your traffic.",
        "Information may also be disclosed when reasonably necessary to comply with law, respond to lawful process, protect users or systems, investigate abuse, or complete a merger, financing, reorganization, or transfer of the Service with appropriate safeguards.",
        "The standard Gateway product does not sell personal information or share it for cross-context behavioral advertising.",
      ],
    },
    {
      id: "retention",
      title: "7. Retention",
      paragraphs: [
        "Retention depends on the deployment configuration, operational needs, security requirements, and applicable agreements. Account and workspace configuration is generally retained while the account or deployment remains active. Sessions remain until they expire, are revoked, or are deleted. Logs may have a separate Operator-configured retention period.",
        "The Operator may retain limited information longer where required for security, backups, legal compliance, dispute resolution, or enforcement. Deletion from active systems may not immediately remove data from protected backups, which is removed or overwritten under the Operator's backup lifecycle.",
      ],
    },
    {
      id: "security",
      title: "8. Security",
      paragraphs: [
        "Gateway is designed to support controls such as hashed passwords and session tokens, HTTP-only cookies, encrypted endpoint and provider credentials, access roles, credential rotation, and security logging. The Operator is responsible for configuring, hosting, monitoring, and maintaining its deployment securely.",
        "No storage or transmission method is completely secure. Protect your account, application keys, provider credentials, and devices, and notify the Operator promptly if you suspect unauthorized access.",
      ],
    },
    {
      id: "international-transfers",
      title: "9. Data location and international transfers",
      paragraphs: [
        "Data is stored and processed in locations chosen by the Operator and its infrastructure providers. Requests may also be sent to upstream providers in other jurisdictions. Where required, the Operator is responsible for using an appropriate transfer mechanism and providing deployment-specific location information.",
      ],
    },
    {
      id: "rights",
      title: "10. Your choices and rights",
      paragraphs: [
        "Depending on applicable law, you may have rights to access, correct, delete, restrict, or obtain a copy of personal information, or to object to or withdraw consent for certain processing. These rights can be limited where processing is required for security, contract performance, legal obligations, or the rights of others.",
        "Contact your workspace administrator or the Operator to make a request. The Operator may need to verify your identity and authority. If your account is managed by an organization, that organization may need to handle the request as the responsible party.",
      ],
    },
    {
      id: "children",
      title: "11. Children",
      paragraphs: [
        "The Service is technical infrastructure intended for organizations and developers. It is not directed to children, and the Operator does not knowingly seek personal information from children who cannot legally consent to this processing in their jurisdiction.",
      ],
    },
    {
      id: "changes-and-contact",
      title: "12. Changes and contact",
      paragraphs: [
        "This policy may be updated to reflect product, legal, or operational changes. The updated date will appear above, and material changes may be communicated through the Service or your workspace administrator.",
        "For privacy questions, requests, or complaints, contact the Operator identified by your organization or deployment administrator. You may also have the right to complain to the data protection authority in your jurisdiction.",
      ],
    },
  ],
};

export function getLegalDocument(kind: LegalDocumentKind): LegalDocument {
  return kind === "terms" ? terms : privacy;
}
