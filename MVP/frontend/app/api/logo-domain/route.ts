import { NextRequest, NextResponse } from 'next/server';

const LOGO_DEV_SECRET_KEY = process.env.LOGO_DEV_SECRET_KEY;

interface BrandSearchResult {
  name: string;
  domain: string;
  logo_url?: string;
}

interface BrandSearchResponse {
  data: BrandSearchResult[];
}

/**
 * GET /api/logo-domain?name=CompanyName
 * 
 * Server-side route that resolves a company name to its domain using Logo.dev Brand Search API.
 * This is necessary because the client-side can only use the publishable key for fetching logos,
 * but resolving company names to domains requires the secret key.
 * 
 * Returns: { domain: "company.com" } or { domain: null } if not found
 */
export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const companyName = searchParams.get('name');

  // Validate input
  if (!companyName) {
    return NextResponse.json(
      { error: 'Missing "name" query parameter', domain: null },
      { status: 400 }
    );
  }

  // Check if secret key is configured
  if (!LOGO_DEV_SECRET_KEY) {
    console.warn('[logo-domain] LOGO_DEV_SECRET_KEY not configured, returning null');
    return NextResponse.json({ domain: null });
  }

  try {
    // Call Logo.dev Brand Search API
    const searchUrl = `https://api.logo.dev/search?q=${encodeURIComponent(companyName)}`;
    
    const response = await fetch(searchUrl, {
      headers: {
        'Authorization': `Bearer ${LOGO_DEV_SECRET_KEY}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      console.error(`[logo-domain] Logo.dev API error: ${response.status}`);
      return NextResponse.json({ domain: null });
    }

    const data: BrandSearchResponse = await response.json();

    // Return the first result's domain if found
    if (data.data && data.data.length > 0) {
      const bestMatch = data.data[0];
      return NextResponse.json({ 
        domain: bestMatch.domain,
        name: bestMatch.name,
      });
    }

    // No results found
    return NextResponse.json({ domain: null });

  } catch (error) {
    console.error('[logo-domain] Error calling Logo.dev API:', error);
    return NextResponse.json({ domain: null });
  }
}


