import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const products = defineCollection({
	loader: glob({ pattern: '**/*.{md,mdx}', base: './src/content/products' }),
	schema: z.object({
		title: z.string(),
		description: z.string().max(180),
		category: z.enum(['rock', 'sport', 'mythology', 'art']),
		image: z.string(),
		imageAlt: z.string(),
		ozonUrl: z.string().url(),
		shopName: z.string(),
		ozonSku: z.string(),
		sellerSku: z.string().optional(),
		sourceKey: z.string().optional(),
		sourceType: z.enum(['order', 'published']).optional(),
		soldUnits: z.number().int().nonnegative(),
		keywords: z.array(z.string()).default([]),
		updatedAt: z.coerce.date(),
		draft: z.boolean().default(false),
	}),
});

export const collections = { products };
