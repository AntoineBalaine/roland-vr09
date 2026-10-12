import type { APIRoute } from "astro";
import { getMapping, postMapping } from "../../lib/library";

export const prerender = false;
export const GET: APIRoute = ({ request }) => getMapping(request);
export const POST: APIRoute = ({ request }) => postMapping(request);
