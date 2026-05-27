// dashboard/middleware.ts
import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  // Refresh session — must call getUser() not getSession()
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;

  // ── Public marketing landing — no auth required ──
  // Static assets the landing page depends on (the page itself + its video).
  // Fonts load from Google's CDN, so nothing else needs whitelisting here.
  if (pathname === "/landing.html" || pathname.startsWith("/videos/")) {
    return supabaseResponse;
  }
  // Root: logged-out visitors see the premium marketing landing; logged-in
  // users continue to the product home exactly as before.
  if (pathname === "/") {
    if (!user) {
      return NextResponse.rewrite(new URL("/landing.html", request.url));
    }
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  // If logged in and on login page → land on the old stable dashboard.
  if (user && pathname === "/login") {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  // If not logged in and not on login page → redirect to login
  if (!user && pathname !== "/login") {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // Non-admin on /admin → send back to the product home (admin gate stays).
  if (user && pathname.startsWith("/admin")) {
    const isAdmin = user.user_metadata?.role === "admin";
    if (!isAdmin) {
      return NextResponse.redirect(new URL("/home/watch", request.url));
    }
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
