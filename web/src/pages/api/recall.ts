import type { APIRoute } from "astro";
import { getRecall } from "../../lib/library";

export const prerender = false;
export const GET: APIRoute = ({ request }) => getRecall(request);
