import type { APIRoute } from "astro";
import { getMappings } from "../../lib/library";

export const prerender = false;
export const GET: APIRoute = ({ request }) => getMappings(request);
