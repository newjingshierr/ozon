# ArtBox World

Russian-language SEO landing site for themed flags, posters, and wall art with product links to Ozon.

## Commands

```sh
npm install
npm run dev
npm run build
```

## Add a product

Create a Markdown file in `src/content/products/` with this frontmatter:

```yaml
---
title: "Название товара"
description: "Короткое описание до 180 символов."
category: rock
image: "/images/product-slug.jpg"
imageAlt: "Описание изображения"
ozonUrl: "https://www.ozon.ru/product/..."
keywords: ["ключевое слово"]
updatedAt: 2026-07-18
draft: false
---
```

Put the product image in `public/images/` and write the Russian page content below the frontmatter. The catalog page, product route, metadata, structured data, and sitemap are generated automatically.

```sh
npm create astro@latest -- --template minimal
```

> 🧑‍🚀 **Seasoned astronaut?** Delete this file. Have fun!

## 🚀 Project Structure

Inside of your Astro project, you'll see the following folders and files:

```text
/
├── public/
├── src/
│   └── pages/
│       └── index.astro
└── package.json
```

Astro looks for `.astro` or `.md` files in the `src/pages/` directory. Each page is exposed as a route based on its file name.

There's nothing special about `src/components/`, but that's where we like to put any Astro/React/Vue/Svelte/Preact components.

Any static assets, like images, can be placed in the `public/` directory.

## 🧞 Commands

All commands are run from the root of the project, from a terminal:

| Command                   | Action                                           |
| :------------------------ | :----------------------------------------------- |
| `npm install`             | Installs dependencies                            |
| `npm run dev`             | Starts local dev server at `localhost:4321`      |
| `npm run build`           | Build your production site to `./dist/`          |
| `npm run preview`         | Preview your build locally, before deploying     |
| `npm run astro ...`       | Run CLI commands like `astro add`, `astro check` |
| `npm run astro -- --help` | Get help using the Astro CLI                     |

## 👀 Want to learn more?

Feel free to check [our documentation](https://docs.astro.build) or jump into our [Discord server](https://astro.build/chat).
