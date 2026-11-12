// SPDX-License-Identifier: Apache-2.0
// Content collections: Starlight docs, plus blog fields (date, author) on the same collection.
import { defineCollection } from 'astro:content';
import { z } from 'astro/zod';
import { docsLoader } from '@astrojs/starlight/loaders';
import { docsSchema } from '@astrojs/starlight/schema';

export const collections = {
  docs: defineCollection({
    loader: docsLoader(),
    schema: docsSchema({
      extend: z.object({
        // Blog posts only (src/content/docs/blog/): publication date and byline.
        date: z.coerce.date().optional(),
        author: z.string().optional(),
        // Docs pages: how much of the page is real today. Shown as a badge in the page header.
        status: z.enum(['works-today', 'in-review', 'planned', 'mixed']).optional(),
      }),
    }),
  }),
};
