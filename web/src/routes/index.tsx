import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  beforeLoad: () => {
    throw redirect({ to: "/u/$userId", params: { userId: "1" } });
  },
  head: () => ({
    meta: [
      { title: "FirstIn — internship scout for students" },
      { name: "description", content: "FirstIn finds real internships early, skips ghost jobs, and prepares applications you send yourself." },
      { property: "og:title", content: "FirstIn — internship scout for students" },
      { property: "og:description", content: "Real internships, found early. You send; FirstIn never does." },
    ],
  }),
});
