import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { Eyebrow, SiteShell } from "./Landing";

// The Terms of Use and the Privacy Policy. They describe the platform as it works today. When the wording changes in a way people
// must agree to again, change EFFECTIVE here AND TERMS_VERSION in backend/app/services/legal.py (sign-up records that version).
const EFFECTIVE = "3 November 2026";
const NAME = "Cover Founder";
const EMAIL = "coverfounder@gmail.com";
const GOVERNING_LAW = "the Federal Republic of Nigeria";

type Table = { head: string[]; rows: string[][] };
type Item = string | string[] | Table;
type Section = { id: string; title: string; body: Item[] };

const mail = <a className="underline hover:text-brand-green" href={`mailto:${EMAIL}`}>{EMAIL}</a>;

function Block({ item }: { item: Item }) {
  if (typeof item === "string") {
    const lead = /^(\d+\.\d+ [^.]+\.)(.*)$/s.exec(item); // "7.1 Licence." leads its paragraph in bold
    return <p className="mt-3 leading-relaxed text-white/85">{lead ? <><strong className="text-white">{lead[1]}</strong>{lead[2]}</> : item}</p>;
  }
  if (Array.isArray(item)) return <ul className="mt-3 list-disc space-y-1.5 pl-6 text-white/85">{item.map((x) => <li key={x} className="leading-relaxed">{x}</li>)}</ul>;
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[32rem] border-collapse text-left text-sm">
        <thead><tr>{item.head.map((h) => <th key={h} className="border border-white/15 bg-white/5 px-3 py-2 font-bold text-white">{h}</th>)}</tr></thead>
        <tbody>{item.rows.map((r) => <tr key={r[0]}>{r.map((c, i) => <td key={i} className="border border-white/15 px-3 py-2 align-top text-white/85">{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function LegalPage({ title, intro, sections, other }: { title: string; intro: string[]; sections: Section[]; other: { to: string; label: string } }) {
  const { pathname, hash } = useLocation();
  // Opening either page (from the footer, a sign-up link or the other page) always starts at the top, unless the link points at a section.
  useEffect(() => {
    const section = hash ? document.getElementById(decodeURIComponent(hash.slice(1))) : null;
    if (section) section.scrollIntoView(); else window.scrollTo(0, 0);
  }, [pathname, hash]);
  useEffect(() => { const old = document.title; document.title = `${title} | ${NAME}`; return () => { document.title = old; }; }, [title]);
  return (
    <SiteShell>
      <main className="px-4 py-10 md:px-8">
        <div className="mx-auto max-w-4xl">
          <Eyebrow>Legal</Eyebrow>
          <h1 className="mt-3 text-3xl text-white md:text-5xl">{title}</h1>
          <p className="mt-3 text-sm text-white/60">Effective {EFFECTIVE}. <Link className="underline hover:text-brand-green" to={other.to}>{other.label}</Link></p>
          {intro.map((p) => <p key={p} className="mt-4 leading-relaxed text-white/85">{p}</p>)}
          <nav aria-label="Contents" className="mt-8 rounded-sm border border-white/15 bg-white/[0.03] p-5">
            <p className="font-mono text-xs font-bold uppercase tracking-[0.2em] text-brand-peach">Contents</p>
            <ol className="mt-3 columns-1 gap-8 space-y-1 text-sm md:columns-2">
              {sections.map((s, i) => <li key={s.id} className="break-inside-avoid"><a className="inline-flex min-h-10 items-center text-white/80 hover:text-brand-green md:min-h-0" href={`#${s.id}`}>{i + 1}. {s.title}</a></li>)}
            </ol>
          </nav>
          {sections.map((s, i) => (
            <section key={s.id} id={s.id} aria-labelledby={`${s.id}-h`} className="mt-10 scroll-mt-24">
              <h2 id={`${s.id}-h`} className="text-xl font-bold text-white md:text-2xl">{i + 1}. {s.title}</h2>
              {s.body.map((b, j) => <Block key={j} item={b} />)}
            </section>
          ))}
          <p className="mt-12 border-t border-white/15 pt-6 text-sm text-white/60">Questions about this page? Email {mail}.</p>
        </div>
      </main>
    </SiteShell>
  );
}

const TERMS: Section[] = [
  { id: "agreement", title: "Agreeing to these Terms", body: [
    `These Terms of Use (the “Terms”) are a binding agreement between you and ${NAME} (“we”, “us”, “our”). They apply to the ${NAME} website at www.coverfounder.com and to everything we offer through it: the AI Newsroom (AI interview, press release, social post and news video), Latest Stories and CF News, Press Distribution, credits and payments, referrals, analytics and your account (together, the “Service”).`,
    "By ticking the box on the sign-up form, creating an account, or using the Service, you confirm that you have read and agree to these Terms and to our Privacy Policy, and that you agree to the specific permissions in section 7 (Permission to publish and share your videos and stories). If you do not agree, do not create an account or use the Service.",
    "If you use the Service for a business, you confirm that you are authorised to bind that business, and “you” includes the business.",
  ] },
  { id: "eligibility", title: "Who can use the Service", body: [
    "You must be at least 18 years old and able to enter a binding contract. The Service is for businesses and the people who run them. It is not meant for children.",
    "You must give accurate sign-up details (business name, city, country, industry and email address) and keep them up to date. You may not use the Service if we have previously removed you from it, or if the law of your country forbids it.",
  ] },
  { id: "service", title: "What the Service does", body: [
    "The Service helps a business turn an announcement into a news-style video and a published story, and helps it reach media outlets. In summary:",
    [
      "You enter the details of an announcement, then take a short on-camera interview with an AI interviewer. Your answers are recorded.",
      "We write a press release and a social post from your details and answers. You can review and edit the press release, and you approve the script before anything is made.",
      "We produce a news video presented by an AI-generated presenter, with your own recorded answers inside it. You can download it, share it by private link and post it yourself.",
      "Finished videos with a written story are published on our website (Latest Stories) unless you remove them, as explained in section 7.",
      "Through Press Distribution you can pay credits to have your announcement, and optionally your video, sent to media outlets you choose. We then contact each outlet and track the result.",
      "You can buy credits, refer other businesses for rewards, and see audience measurements for your videos.",
    ],
    "We may add, change, pause or remove features at any time, including features that are switched off or marked “coming soon”.",
  ] },
  { id: "account", title: "Your account and security", body: [
    "Sign-up needs a confirmed email address (we send a 6-digit code) and a password. You are responsible for everything done through your account and for keeping your password and email access secure. Tell us straight away at " + EMAIL + " if you think someone else has used your account.",
    "For your protection, sessions end after one hour without activity and you will need to sign in again. One person should not share an account with others; invite us to set up separate access if your team needs it.",
    "We may suspend or close accounts that are inactive, that put the Service or other people at risk, or that break these Terms.",
  ] },
  { id: "ai", title: "AI-generated content", body: [
    "Parts of the Service are created by artificial intelligence: the interviewer’s voice and questions, the written press release and social post, the transcript of your answers, and the news presenter in your video, which is an AI-generated avatar and not a real person.",
    [
      "AI output can contain mistakes, omissions or wording you would not choose. You are responsible for reading the press release, script and video and for approving only what is accurate and what you are happy to publish. Nothing paid is made until you approve.",
      "We flag statements about money, funding, user numbers, rankings and superlatives so you can check them, and we word unverified claims cautiously. A flag or a hedge is not a check by us. We do not verify the facts you give us.",
      "Your recorded answers are your own statements. We do not rewrite what you say in your answers, although we may trim, level the sound of, caption and place them in the video.",
      "The presenter is AI-generated. You must not present the presenter as a real journalist or claim the video is independent reporting by a real news organisation. Where we show a video, we tell viewers that the presenter is AI-generated and that the business story is recorded by real people. When you share a video, please keep that disclosure where you can.",
    ],
    "The Service is not legal, financial, investment or public-relations advice. A press release made on the Service is not an offer or a solicitation to buy or sell any security or other financial product.",
  ] },
  { id: "content", title: "Your content and what you promise us", body: [
    "“Your Content” means everything you give us or make through the Service: your announcement text and details, your name, role, company, city, country, website and logo, your recordings (video, audio and snapshots), transcripts, pictures you upload, edits you make, and the press release, social post and video we generate from them.",
    "You keep ownership of Your Content, and the rights you had in it before using the Service. We own the Service itself: the software, templates, graphics, music, the AI presenter and our brand, and nothing in these Terms transfers them to you. You may use the finished video and written material for your own lawful business purposes, for example on your website, in investor updates and on your social media.",
    "You promise that:",
    [
      "everything you tell us is true, not misleading and not defamatory, and you have the right to share it;",
      "you own, or have permission to use, everything you upload, including pictures, logos, music, names and any third-party material;",
      "every other person who appears in, speaks in or is named in your material (for example a co-founder or a customer) has agreed to it being used as set out in these Terms, or you have the right to give that agreement for them;",
      "you will not include confidential information, trade secrets or personal data about other people that you have no right to share; and",
      "your announcement does not break any law, regulation, advertising or securities rule, or anyone else’s rights.",
    ],
  ] },
  { id: "permission", title: "Permission to publish and share your videos and stories", body: [
    "This section is important. It gives us specific permissions so that your story can be seen as widely as possible. By ticking the box at sign-up, and by creating, approving or publishing a video or story, you expressly agree to the following.",
    "7.1 Licence. You give us a worldwide, non-exclusive, royalty-free licence, with the right to sublicense to the platforms and outlets we use, to host, store, copy, edit, format, caption, crop, clip, excerpt, translate into captions, reproduce, display, perform, publish, distribute and promote Your Content that is part of a finished video or story (including the video, press release, headline, summary, thumbnail, social post, quotes, pictures and logo), for the purposes in 7.2.",
    "7.2 What we may do with it. We may:",
    [
      "publish it automatically on the Cover Founder website, including Latest Stories and, where suitable, CF News, once your video is finished (the media contact details in your press release are not shown publicly);",
      "post, repost, share, pin, clip and promote it on Cover Founder’s own social media and video channels and community groups, for example YouTube, LinkedIn, X, Instagram, Facebook, TikTok and WhatsApp channels, in the form of full videos, shorter clips, images, quotes or links, including by paying to boost our own posts;",
      "feature it in our newsletters, emails, website, presentations, case studies and marketing, to show what the Service can do and to give your business more visibility;",
      "send it to the media outlets you choose through Press Distribution, and to other media and partners where this helps your story reach people, in line with your request; and",
      "use your name, job title, company name, city and country, logo, voice and image as they appear in the video, press release and pictures, in connection with all of the above.",
    ],
    "7.3 Credit and no payment. We will normally name your company when we share your story. We do not pay you a fee or royalty for these uses, and you agree that the free and low-cost production of your video is fair value for them.",
    "7.4 Editing. We may make technical and editorial changes to fit a format or platform (length, shape, captions, thumbnails). We will not change the meaning of your recorded answers.",
    "7.5 How long it lasts and how to stop it. The permissions in 7.2 last for as long as your video or story is published or promoted by us. You can ask us to unpublish your story at any time and we will do so promptly; we will also stop promoting it and will take down our own social posts that we control as soon as reasonably possible. Taking something down does not undo copies already shared, saved or reposted by other people or platforms, or sent to outlets under a distribution request, and we cannot recall them. Withdrawing your permission does not affect earlier uses. We may keep a private archive copy for our records, security and legal needs.",
    "7.6 Your confirmation. You confirm that you have the right to give these permissions, including the permission of any other person who appears in or is named in your material.",
  ] },
  { id: "use", title: "Rules for using the Service", body: [
    "You must not use the Service to:",
    [
      "publish anything unlawful, false or misleading, including misleading claims about funding, returns, users, partnerships, regulatory approval or results;",
      "promote scams, pyramid or pump-and-dump schemes, unlicensed financial offers, illegal products, weapons, adult content or anything that could harm people;",
      "harass, threaten, defame, discriminate against or abuse anyone, or include hate speech;",
      "impersonate any person or organisation, or give a false identity or business;",
      "upload malware, or anything you do not have the right to upload;",
      "copy, scrape, resell or build a competing service from the Service, reverse-engineer it, or get around its limits, payment, credit or security controls; or",
      "use bots or automated means to sign up, create videos or submit distribution requests.",
    ],
    "Do not remove or hide the disclosure that the presenter is AI-generated.",
  ] },
  { id: "moderation", title: "Review, moderation and removal", body: [
    "We screen announcements, scripts, press releases and recordings, using automated checks and sometimes people. We may hold content for review, ask you to change or re-record it, refuse to make or publish it, or remove it, if we think it could break these Terms, the law or someone’s rights, or could harm our users, our partners or our reputation. An answer that has no speech, is too short, is too dark or contains abusive language may need to be recorded again.",
    "We can unpublish any story or video, suspend sharing for an account, and decline or stop any distribution request. Where we can, and where it is safe and lawful to do so, we will tell you why. We have no duty to monitor everything on the Service.",
  ] },
  { id: "credits", title: "Credits, prices and payments", body: [
    "The Service runs on credits. At the date above, one video costs one credit, and a new account receives one free credit. Distribution to each outlet has its own price in credits, shown to you, with any logo or extra-picture fee, before you submit. We show the price first; we do not charge you without telling you.",
    [
      "Buying credits: you can add credits by card. Payments are made on the hosted page of our payment provider, Stripe, and are in US dollars. The lowest amount you can add is shown on the billing page. We never see or store your full card number.",
      "Credits have no cash value, cannot be transferred or exchanged for money, and are used for the Service only. We may change prices and the credit cost of features for the future; changes do not affect credits you have already spent.",
      "Failed videos: if a video cannot be made because of a fault on our side, you are not charged for it, or we restore the credit.",
      "Refunds: payments for credits are final once credits are added, except where the law gives you a right to a refund, where we charged you in error, or where we agree otherwise in writing. Contact us at " + EMAIL + " with the payment reference. If a refund is made, we may remove the matching unspent credits.",
      "Chargebacks: if you dispute a payment with your bank without first contacting us, we may hold or remove the matching credits and suspend the account while the dispute is open.",
      "Taxes: prices do not include any taxes or bank charges that apply to you, unless we say they do.",
    ],
  ] },
  { id: "distribution", title: "Press Distribution", body: [
    "Press Distribution lets you choose media outlets and pay credits for us to submit your announcement and, if you choose, your video to them.",
    [
      "No guarantee. Outlets are independent. We cannot promise that an outlet will publish your story, when, in what form, or what reach it will have. An outlet may edit, delay, decline or remove your story. Customer-visible statuses (Pending, In progress, Published) show our progress and the outlet’s actions.",
      "Your request. When you submit, you confirm the details are accurate, you have the rights to everything you send (including logos and pictures), and you consent to us sharing them, with your name, contact details and company, with each outlet you chose and with our team and service providers who handle the request.",
      "Credits. The credits shown at submission are taken once, and a confirmation number and receipt are provided. If we are unable to submit to an outlet, we will tell you and may offer a replacement outlet or return the credits for that outlet at our discretion. Credits are not returned because an outlet chooses not to publish.",
      "Outlet fees. Some outlets charge fees, or accept logos or extra pictures for a fee, as shown in your quote. We do not control third-party editorial decisions.",
      "Regions. Availability depends on the outlets listed at the time. Regions marked “coming soon” are not yet available.",
    ],
  ] },
  { id: "referrals", title: "Referral programme", body: [
    "You may share your personal referral link. When a new business signs up using it and confirms its email, you receive the credit reward shown on your Referral page, and a further reward the first time that business pays credits for a distribution, once per referred business. Rewards are credits only.",
    "You may not refer yourself or your own other accounts, use fake accounts or misleading promotion, or spam. We may withhold or remove rewards for abuse, and we may change or end the programme at any time.",
  ] },
  { id: "public", title: "Public pages, sharing and measurement", body: [
    "Published stories are public: anyone with the link, and anyone browsing Latest Stories, can see the video, headline, summary and press release, without your media contact details. You can share a video privately with a link that you can switch off. Search engines and link-preview tools may display public stories.",
    "We measure how people view stories and shared videos (for example visits, engaged views and completions) and show you the results. These measurements describe recorded sessions and are estimates, not verified unique people. Publisher figures depend on outlets sending them to us.",
  ] },
  { id: "ip", title: "Our rights and feedback", body: [
    "The Service, the AI presenter, our templates, graphics, software, designs and the Cover Founder name and logo belong to us or our licensors. Except for the video and written material we create for you, you receive only the right to use the Service as these Terms allow.",
    "If you send us ideas or feedback, we may use them freely without paying you.",
  ] },
  { id: "third", title: "Third-party services", body: [
    "The Service relies on third parties, including providers of hosting, storage, payments, email, AI writing, voice and transcription, AI presenter video and live video. Media outlets and social platforms are independent of us. We are not responsible for their services, policies or actions, and your use of them may be subject to their terms.",
  ] },
  { id: "disclaimer", title: "Disclaimers", body: [
    "To the fullest extent the law allows, the Service is provided “as is” and “as available”. We do not promise that it will be uninterrupted, error-free or secure, that AI output will be accurate or suitable, that a video will be ready by a certain time, or that your story will be published, noticed or have any commercial result.",
    "Nothing in these Terms removes rights that the law gives you and that cannot be excluded.",
  ] },
  { id: "liability", title: "Limit of our liability", body: [
    "To the fullest extent the law allows, we are not liable for indirect, incidental, special, consequential or punitive loss, or for lost profit, revenue, goodwill, data or business opportunity, arising from your use of the Service, including from content published by you, by us on your behalf under section 7, or by an outlet.",
    "Our total liability to you for all claims relating to the Service in any 12-month period is limited to the amount you paid us for credits in that period, or, if you have not paid anything, to US$100.",
    "Nothing in these Terms limits liability that cannot be limited by law, such as liability for fraud or for death or personal injury caused by negligence.",
  ] },
  { id: "indemnity", title: "Your responsibility for claims", body: [
    "You agree to defend and compensate us, our team, partners and service providers against claims, losses and costs (including reasonable legal fees) arising from Your Content, from your breach of these Terms or the law, or from your claims about your business, including claims that Your Content is false, defamatory or infringes anyone’s rights, or that you did not have permission to give the permissions in section 7.",
  ] },
  { id: "ending", title: "Ending your use", body: [
    "You can stop using the Service at any time and can export or delete your data from Settings (see our Privacy Policy). We can suspend or end your access at any time if you break these Terms, if the law requires, or if we stop the Service, and we will give notice where we reasonably can.",
    "When an account ends, unused credits are lost unless the law or we say otherwise. Sections that by their nature should continue (including sections 6, 7.5, 10, 14, 16 to 18 and 21) continue to apply.",
  ] },
  { id: "changes", title: "Changes to these Terms", body: [
    "We may update these Terms. We will post the new version with its effective date, and where a change matters to you we will tell you, for example by email or a notice in the app. If you keep using the Service after the change takes effect you accept the new Terms; if you do not agree, stop using the Service and tell us.",
  ] },
  { id: "law", title: "Governing law and disputes", body: [
    `These Terms are governed by the laws of ${GOVERNING_LAW}, and its courts have jurisdiction over disputes about them, unless the mandatory consumer or data-protection law where you live gives you the right to bring a claim somewhere else. Please contact us first at ${EMAIL} so we can try to resolve the problem informally.`,
    "If a part of these Terms is found unenforceable, the rest still applies. If we do not enforce a right straight away, we have not given it up. These Terms and the Privacy Policy are the whole agreement between you and us about the Service. You may not transfer your rights under them without our consent; we may transfer ours as part of a merger, sale or reorganisation.",
  ] },
  { id: "contact", title: "Contact us", body: [
    `${NAME}. Email: ${EMAIL}. Please include your account email and, for payments, the payment reference.`,
  ] },
];

const PRIVACY: Section[] = [
  { id: "who", title: "Who we are", body: [
    `${NAME} (“we”, “us”) runs the ${NAME} platform at www.coverfounder.com. We are responsible for the personal data described in this policy (the “controller”). Contact us about privacy at ${EMAIL}.`,
    "This policy explains what personal data we collect, why, who we share it with, how long we keep it and the choices you have. It applies to people who create an account, to people who appear in or are named in videos and stories, to publisher contacts, and to visitors to our website.",
  ] },
  { id: "collect", title: "What we collect", body: [
    { head: ["What", "Examples", "Where it comes from"], rows: [
      ["Account details", "Email address, password (stored only as a one-way hash), business name, city, country, industry, sign-up date, the version of the Terms and Privacy Policy you agreed to and when", "You"],
      ["Announcement details", "The announcement text, type of announcement, your first and last name, role, company, city and country, website, chosen presenter", "You"],
      ["Interview recordings", "Video and audio of your answers, snapshots of your answers, the transcript of what you say, quality checks (for example whether there is speech and enough light)", "You, and our transcription provider"],
      ["Generated and edited content", "The press release, headline, summary, social post, script, edits you make, pictures and logos you upload, and the finished video, captions and thumbnail", "You and the AI tools we use"],
      ["Public story data", "What is shown on Latest Stories and CF News: video, headline, summary, press release, pictures, company, dateline", "You (published by us under the Terms)"],
      ["Payments and credits", "Credit purchases, amounts, dates, payment reference, receipts and invoices, the credit ledger. Card details are entered on Stripe and never reach us", "You and Stripe"],
      ["Distribution", "Outlets you chose, contact name and email, logos, pictures, request and status history, outlet messages and published links", "You and outlets"],
      ["Referrals", "Your referral code, who joined with it, rewards earned. We never show a referred person’s email address to the referrer", "You and referred businesses"],
      ["Usage and audience data", "Views of stories and shared videos (visits, engaged views, completion), page and feature use, a random per-tab session identifier that we keep only as a one-way digest", "Your device"],
      ["Website visits (counted without cookies)", "Which pages are opened and where visitors came from. We turn your IP address and browser details into a one-way code that changes every day, keep only daily totals, and never store your IP address for this. Nothing is stored on your device", "Your device"],
      ["Website analytics with Google Analytics", "Pages visited and steps reached (such as signing up or buying credits), with approximate location and basic device and browser details. Counted without cookies until you choose; uses cookies only if you accept; switched off if you decline. Private link codes, your name, email and company name are never included", "Your device, through Google Analytics"],
      ["Technical and security data", "IP address, browser and device type, sign-in and session records, error logs, audit records of changes", "Your device and our systems"],
      ["Messages", "Emails and messages you send us, and our emails to you (codes, receipts, video-ready, distribution updates)", "You and us"],
    ] },
    "We do not use facial recognition and we do not identify you from your face or voice. The camera check outline is only an on-screen guide.",
    "Do not give us sensitive personal data (such as health, religion, political opinions or government ID numbers) or personal data about other people unless the announcement truly needs it and you have the right to share it.",
  ] },
  { id: "use", title: "How we use it and why", body: [
    { head: ["Purpose", "Legal basis (where the law requires one)"], rows: [
      ["Create and secure your account; make your interview, press release, social post and video; deliver downloads, links and email notices", "Contract: to provide the Service you asked for"],
      ["Publish your finished story on our website, share it on our social media and in our marketing, and send it to media outlets you choose", "Your consent (given at sign-up and when you create or publish a video) and contract. You can withdraw consent as explained in section 8"],
      ["Take payments, give credits, send receipts, prevent fraud and keep financial records", "Contract, legal obligation and our legitimate interest in preventing fraud"],
      ["Screen content for safety (automated checks and human review), enforce our Terms, keep the Service secure, fix errors", "Our legitimate interests in running a safe service, and legal obligation"],
      ["Measure how stories are viewed and show you your results; improve the Service", "Our legitimate interests (we use limited, first-party measurement)"],
      ["Count visits to our website and app without cookies, and understand how they are used with Google Analytics, so we can improve them", "Our legitimate interests, for the cookie-free counting and for Google Analytics before you choose (a browser’s Do Not Track or Global Privacy Control signal stops both). Your consent, for analytics cookies. If you decline, Google Analytics is switched off for you"],
      ["Run referrals and rewards", "Contract and legitimate interests"],
      ["Contact you about your account, service updates and, where allowed, news about our features (you can opt out of marketing)", "Contract, legitimate interests and, where required, consent"],
      ["Comply with law and respond to lawful requests", "Legal obligation"],
    ] },
    "We do not sell your personal data. We use your recordings and content to deliver the Service to you and as set out in the Terms; we do not ourselves use them to train artificial intelligence models.",
  ] },
  { id: "social", title: "Public sharing and social media", body: [
    "By agreeing to the Terms, you consent to us publishing your finished videos and stories on our website and sharing them on our social media channels and other marketing, together with your name, role, company, location, logo, voice and image as they appear in the material (see section 7 of the Terms).",
    "Published content is public. It may be seen, copied and shared by anyone, found by search engines, and reposted on platforms we do not control. Those platforms and recipients handle personal data under their own policies, and we cannot control or fully remove copies they hold.",
    "You can ask us to unpublish a story or stop sharing a video at any time (section 8). We will stop our own use and take down posts we control as soon as reasonably possible.",
  ] },
  { id: "share", title: "Who we share it with", body: [
    "We share personal data only as needed, with:",
    [
      "media outlets and publishers you choose in Press Distribution, who receive your announcement, video, contact details, logo and pictures;",
      "social media and video platforms, when we post your story on our channels (see above);",
      "service providers who process data for us under contract, such as those in the table below;",
      "the public, for stories we publish;",
      "advisers, auditors, insurers and authorities, when the law requires or to protect rights and safety; and",
      "a buyer or successor, if our business is sold or reorganised (with the same protection for your data).",
    ],
    { head: ["Type of provider", "What they do", "Examples (depending on setup)"], rows: [
      ["Hosting and storage", "Run the website, our servers and databases, and store files such as recordings and videos", "Vercel, Railway, Cloudflare R2"],
      ["AI writing, voice and transcription", "Write the story, speak the interviewer’s questions, and turn your answers into text", "OpenAI and Anthropic, or compatible providers"],
      ["AI presenter video", "Create the AI presenter’s parts of your video", "HeyGen, Synthesia"],
      ["Live interview (optional)", "Carry the live camera session", "LiveKit"],
      ["Payments", "Process card payments on their own hosted page", "Stripe"],
      ["Email", "Send codes, receipts and notices", "Resend or an email service we configure"],
      ["Security and quality", "Scan uploads for malware, monitor errors", "ClamAV, Sentry"],
      ["Website analytics", "Show us which pages are used and where people leave, so we can improve the Service. Counts visits without cookies until you choose, and uses cookies only if you accept", "Google Analytics and Google Tag Manager (Google)"],
    ] },
    "These providers may only use the data to provide their service to us, and must protect it. The list can change; we will keep this policy current.",
  ] },
  { id: "transfers", title: "International transfers", body: [
    "We and our providers work internationally, so your data may be processed in countries other than your own, including countries that may not have the same data-protection laws. Where required, we use safeguards such as contracts with data-protection terms. Because stories are public and outlets are in several countries, published and distributed content can be seen worldwide.",
  ] },
  { id: "keep", title: "How long we keep it", body: [
    { head: ["Data", "How long"], rows: [
      ["Raw interview recordings", "Deleted 90 days after your video is finished, unless you choose to keep them"],
      ["Finished videos, press releases and social posts", "While your account is open, and for published stories, while published. A private archive copy may be kept for records and security"],
      ["Account details", "While your account is open, then deleted or anonymised after closure, except what we must keep"],
      ["Payment, credit-ledger and invoice records", "For the period the law requires for financial and tax records"],
      ["Distribution requests and outlet history", "While your account is open, and as needed for records and disputes"],
      ["Sign-in sessions", "End after one hour without activity; session records are kept for security for a limited time"],
      ["Audit and security logs, consent records", "For as long as needed for security, to prove your agreement, and to meet legal duties"],
      ["Audience measurements", "Daily totals are kept; detailed event records are removed on a regular schedule"],
      ["Website visit counts", "Daily totals are kept. The daily one-way codes used to avoid counting a visitor twice in a day are deleted after two days"],
    ] },
  ] },
  { id: "rights", title: "Your rights and choices", body: [
    "Depending on where you live (for example under the Nigeria Data Protection Act 2023, the UK and EU GDPR, Canada’s PIPEDA, or US state laws), you may have the right to:",
    [
      "ask for a copy of your personal data and for it to be corrected;",
      "ask us to delete it, or restrict or object to how we use it;",
      "receive your data in a portable form;",
      "withdraw consent at any time (for example, ask us to unpublish your story and stop sharing it), without affecting earlier use that was lawful;",
      "object to marketing emails (use the unsubscribe link or write to us); and",
      "complain to your data-protection authority, such as the Nigeria Data Protection Commission, the UK Information Commissioner’s Office, an EU supervisory authority or the Office of the Privacy Commissioner of Canada.",
    ],
    `You can export or delete your workspace data from the “Your data” area in Settings, or write to ${EMAIL}. We may ask you to prove who you are first. Some records (such as payment, tax, security and consent records) must be kept, and deletion cannot recall copies already shared by third parties or sent to outlets.`,
  ] },
  { id: "security", title: "How we protect it", body: [
    "We use passwords stored with strong one-way hashing, emailed confirmation codes, sessions that expire after one hour of inactivity, encrypted connections, signed and expiring file links, malware scanning of uploads, rate limits, access controls for our team (each person only sees what their role needs), and audit logs. Card numbers are handled by Stripe and never reach our servers.",
    "No system is perfectly secure. If a breach affects your personal data, we will tell you and the authorities as the law requires.",
  ] },
  { id: "automated", title: "AI and automated checks", body: [
    "We use AI to write content, create the presenter and voice, transcribe your answers and screen content. These tools help us make and review your material; they are not used to make solely automated decisions that have legal or similarly significant effects on you. If an automated check blocks or holds your content, a person can review it, and you can contact us.",
  ] },
  { id: "storage", title: "Cookies and similar storage", body: [
    "We use what the Service needs: your sign-in token, small settings in your browser (such as the collapsed menu, notices you have closed, your cookie choice and which notifications you have read), a referral code held for the length of your visit, and a random per-tab identifier for audience measurement, kept only as a one-way digest. Blocking this storage may stop parts of the Service working.",
    "Cookie-free visit counting. We count visits to our website and app ourselves, without any cookie or other storage on your device. We turn your IP address and browser details into a one-way code that changes every day, so we can count you once a day but cannot follow you from one day to the next, and we do not store your IP address for this. We keep only daily totals: how many visitors, which pages, and where they came from (for example a search engine, a social network, another website, or one of our emails). Robots, our team’s back office and private interview and share links are never counted.",
    "Google Analytics and Google Tag Manager. We also use Google Analytics, a service of Google, to understand how our website and app are used, and we load our measurement tags through Google Tag Manager, a Google tool for managing them. Google receives your IP address and basic browser details when these load, as it does for any website you visit. Until you choose, it counts your visit without setting any cookie: it receives the page you opened, your IP address and basic browser details. If you click Accept in the cookie notice, it also sets cookies (named _ga and _ga_ followed by an identifier) that last up to 13 months, so it can recognise a returning visitor and see how people move around. If you click Decline, Google Analytics is switched off for you. We remove private link codes and project and payment numbers from page addresses before they are sent, and we never send your name, email address or company name. We do not use Google’s advertising features, and we do not use advertising cookies.",
    "Your choice. You can change your mind at any time from Cookie settings in the footer of our website, or in Settings in the app: turning it off switches Google Analytics off and removes its cookies. If your browser sends a Do Not Track or Global Privacy Control signal, we treat it as a refusal: we do not use Google Analytics for you and we do not count your visit.",
  ] },
  { id: "children", title: "Children", body: [
    "The Service is for people aged 18 and over. We do not knowingly collect data from children. If you think a child has given us data, contact us and we will delete it.",
  ] },
  { id: "changes", title: "Changes to this policy", body: [
    "We may update this policy. We will post the new version with its effective date and, for important changes, tell you by email or in the app. The version you agreed to at sign-up is recorded against your account.",
    "Most recent change (11 November 2026): we added Google Analytics and our own cookie-free visit counting, described under “Cookies and similar storage”. Analytics cookies are used only if you accept. This does not change what you agreed to at sign-up.",
  ] },
  { id: "contact", title: "Contact us", body: [
    `${NAME}. Privacy questions and requests: ${EMAIL}. Please include your account email so we can find your data.`,
  ] },
];

export function TermsPage() {
  return <LegalPage title="Terms of Use" other={{ to: "/privacy", label: "Read the Privacy Policy" }} sections={TERMS} intro={[
    `Welcome to ${NAME}. Please read these Terms carefully. They explain what you can expect from us and what we expect from you, including your permission for us to publish and share the videos and stories made on the platform so that more people can see them.`,
  ]} />;
}

export function PrivacyPage() {
  return <LegalPage title="Privacy Policy" other={{ to: "/terms", label: "Read the Terms of Use" }} sections={PRIVACY} intro={[
    `Your privacy matters to us. This policy explains how ${NAME} collects, uses, shares and protects personal data when you use our platform, including what happens when your videos and stories are published and shared.`,
  ]} />;
}
