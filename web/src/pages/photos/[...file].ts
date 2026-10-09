import type { APIRoute } from "astro";
import { media } from "../../lib/library";

export const prerender = false;
export const GET: APIRoute = ({ request, params }) => media(request, "photos", params.file ?? "");
