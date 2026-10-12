import type { APIRoute } from "astro";
import { getTones } from "../../lib/library";

export const prerender = false;
export const GET: APIRoute = ({ request }) => getTones(request);
