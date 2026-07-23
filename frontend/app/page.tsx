import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-3xl font-bold">Smart Hiring Platform</h1>
      <p className="text-muted-foreground max-w-md">
        Frontend is up and connected. Backend API base URL:{" "}
        <code className="bg-black/5 dark:bg-white/10 px-1 py-0.5 rounded">
          {process.env.NEXT_PUBLIC_API_BASE_URL}
        </code>
      </p>
      <Link href="/upload" className={cn(buttonVariants({ variant: "default" }))}>
        Get Started
      </Link>
    </main>
  );
}
