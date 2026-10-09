import type { APIRoute } from "astro";
import { postPatch } from "../../lib/library";

export const prerender = false;
export const POST: APIRoute = ({ request }) => postPatch(request);
