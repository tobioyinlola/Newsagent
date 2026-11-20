import type { TourDef } from "../components/tour/tourTypes";

// The guided tours for customers. Progress is saved per person on the server (see lib/onboarding.ts).
export const CUSTOMER_TOURS: TourDef[] = [
  {
    id: "welcome",
    title: "Find your way around",
    summary: "Your dashboard and menu, in about two minutes.",
    steps: [
      { route: "/dashboard", title: "Welcome to Cover Founder", body: "This is where you turn your business story into a news-style video and get it in front of news outlets. Here is a quick look around. You can stop any time and pick up where you left off." },
      { target: "nav-dashboard", title: "Your dashboard", body: "Home base. See your credits, your videos, how many outlets have published you, and what to do next." },
      { target: "nav-videos", title: "Videos", body: "Every video you make lives here, from the first draft to the finished story you can share." },
      { target: "nav-distribution", title: "Distribution", body: "Send your story and video to news outlets. You choose the outlets, we reach out to them, and you can follow each placement." },
      { target: "nav-analytics", title: "Analytics", body: "See how many people are watching and reading your story, and where they come from." },
      { target: "nav-referral", title: "Referral", body: "Invite another business with your personal link. You both get something when they join." },
      { target: "nav-credits", title: "Buy credits", body: "Credits pay for videos and for outlet placements. Your balance is always shown in the menu, and you can top up here." },
      { target: "nav-settings", title: "Settings", body: "Your profile, password, billing and referral details. You can also change the answers you gave when you joined." },
      { route: "/dashboard", target: "dash-next", title: "What to do next", body: "Three steps to your first story: tell us about your business, set up your brand, then choose where to publish it." },
      { target: "tours-menu", title: "Come back any time", body: "Open Guided tours whenever you want a refresher. There are short tours for making a video and for distributing it, and your progress is saved." },
    ],
  },
  {
    id: "first-video",
    title: "Make your first video",
    summary: "What to tell us and what happens next.",
    steps: [
      { route: "/ai-newsroom/new", title: "Your story starts here", body: "You describe your announcement, and we turn it into a news-style video with an AI presenter. It takes a few minutes of your time." },
      { target: "video-kind", title: "What are you announcing?", body: "Pick the closest match, like a launch, a milestone or a product. It helps us choose the right tone and structure." },
      { target: "video-details", title: "Give us the key facts", body: "Who you are, what is happening, who it is for, and any numbers, dates or names to feature. A few clear sentences is plenty." },
      { target: "video-form", title: "Then we take it from here", body: "Add your first name, submit, and we guide you through the next steps. Our AI interviewer asks a few questions, and you review the result before anything is shared." },
    ],
  },
  {
    id: "distribution",
    title: "Get your story published",
    summary: "Choose outlets and send your story to them.",
    steps: [
      { route: "/distribution/request", target: "dist-intro", title: "Distribute your story", body: "Send your announcement and video to news outlets. You pick the outlets, pay with credits, and our team coordinates with them." },
      { target: "outlet-planner", title: "Not sure where to start?", body: "If you see suggested plans here, answer three quick questions about where your readers are, your budget and your goal, and we suggest outlets that fit. You can still choose anything from the full list." },
      { title: "You stay in control", body: "Review your choices and the total before you pay. Outlets decide whether to publish, so placement is requested for you but never guaranteed. You can follow every outlet's progress afterwards." },
    ],
  },
];
