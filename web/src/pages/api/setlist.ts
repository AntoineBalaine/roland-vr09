import type { APIRoute } from "astro";
import { postSetlist } from "../../lib/library";

export const prerender = false;
export const POST: APIRoute = ({ request }) => postSetlist(request);
