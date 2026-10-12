import type { APIRoute } from "astro";
import { postPageLog } from "../../lib/library";

export const prerender = false;
export const POST: APIRoute = ({ request }) => postPageLog(request);
