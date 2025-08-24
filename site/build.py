#!/usr/bin/env python3
import os, csv, datetime, re, json, html, yaml

BASE = os.path.dirname(__file__)
DATA = os.path.join(BASE, "data")
TPL = os.path.join(BASE, "templates")
OUT = os.path.join(BASE, "out")

def read_csv(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
    return rows

def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')

def md_to_html(md):
    lines = md.splitlines()
    out = []
    in_code = False
    in_ul = False
    for line in lines:
        if line.startswith("```"):
            in_code = not in_code
            out.append("<pre><code>" if in_code else "</code></pre>")
            continue
        if in_code:
            out.append(html.escape(line)); continue
        if line.startswith("## "):
            out.append(f"<h2>{html.escape(line[3:])}</h2>"); continue
        if line.startswith("# "):
            out.append(f"<h1>{html.escape(line[2:])}</h1>"); continue
        if line.startswith("- "):
            if not in_ul: out.append("<ul>"); in_ul=True
            out.append(f"<li>{html.escape(line[2:])}</li>"); continue
        else:
            if in_ul: out.append("</ul>"); in_ul=False
        if not line.strip():
            out.append("")
        else:
            out.append(f"<p>{html.escape(line)}</p>")
    if in_ul: out.append("</ul>")
    return "\n".join(out)

def render(tpl, ctx):
    def eval_expr(expr, ctx):
        expr = expr.strip()
        if expr.endswith("|safe"): expr = expr[:-5].strip()
        cur = ctx
        for part in expr.split('.'):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return ""
        return cur

    tokens = re.split(r"(\{\%.*?\%\}|\{\{.*?\}\})", tpl, flags=re.S)
    out = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("{%"):
            stmt = tok[2:-2].strip()
            if stmt.startswith("for "):
                # {% for x in items %}
                m = re.match(r"for\s+(\w+)\s+in\s+(.+)", stmt)
                var, expr = m.group(1), m.group(2)
                # find endfor
                j = i+1; block=[]; depth=1
                while j < len(tokens):
                    if tokens[j].startswith("{%"):
                        s = tokens[j][2:-2].strip()
                        if s.startswith("for "): depth += 1
                        if s == "endfor": depth -= 1
                        if depth == 0: break
                    block.append(tokens[j]); j += 1
                seq = eval_expr(expr, ctx)
                seq = seq or []
                for val in seq:
                    ctx[var] = val
                    out.append(render("".join(block), ctx.copy()))
                i = j
            elif stmt == "endfor":
                pass
        elif tok.startswith("{{"):
            expr = tok[2:-2].strip()
            val = eval_expr(expr, ctx)
            out.append(str(val))
        else:
            out.append(tok)
        i += 1
    return "".join(out)

def write_out(path, content):
    path = os.path.join(OUT, path.lstrip("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def main():
    sitecfg = load_yaml(os.path.join(DATA, "store.yml"))
    site = sitecfg.get("site", {})
    seo = sitecfg.get("seo", {})

    prows = read_csv(os.path.join(DATA, "products.csv"))
    arows = read_csv(os.path.join(DATA, "posts.csv"))

    today = datetime.date.today()
    products = []
    for p in prows:
        p["slug"] = slugify((p.get("sku","") + "-" + p.get("title","")) or p.get("title",""))
        p["tags"] = [t.strip() for t in (p.get("tags","").split(",")) if t.strip()]
        try: p["price"] = "{:.2f}".format(float(p.get("price","0")))
        except: p["price"] = "0.00"
        pub = p.get("publish_date","1970-01-01")
        try:
            pubd = datetime.datetime.strptime(pub, "%Y-%m-%d").date()
        except:
            pubd = today
        if p.get("status","active")=="active" and pubd <= today:
            products.append(p)

    posts = []
    for a in arows:
        a["tags"] = [t.strip() for t in (a.get("tags","").split(",")) if t.strip()]
        try:
            ad = datetime.datetime.strptime(a.get("publish_date","1970-01-01"), "%Y-%m-%d").date()
        except:
            ad = today
        if a.get("status","active")=="active" and ad <= today:
            a["date"] = str(ad)
            a["rfc822"] = datetime.datetime(ad.year, ad.month, ad.day).strftime("%a, %d %b %Y 00:00:00 +0000")
            a["body_html"] = md_to_html(a.get("body_markdown",""))
            posts.append(a)

    jsonld = json.dumps({
      "@context":"https://schema.org",
      "@type":"Store",
      "name": site.get("name",""),
      "url": site.get("url",""),
      "description": seo.get("description","")
    })

    def load_tpl(name):
        return open(os.path.join(TPL, name), "r", encoding="utf-8").read()

    base = load_tpl("base.html")
    def page(content, page_title, meta_description, canonical):
        return render(base, {
            "site": site,
            "seo": seo,
            "jsonld": jsonld,
            "year": today.year,
            "page_title": page_title,
            "meta_description": meta_description,
            "canonical": canonical,
            "content": content
        })

    # Home
    home_html = render(load_tpl("index.html"), {"site": site, "seo": seo, "products": products, "posts": posts})
    write_out("index.html", page(home_html, "Home", seo.get("description",""), site.get("url","")))

    # Products index
    plist_html = render(load_tpl("products_index.html"), {"site": site, "products": products})
    write_out("products/index.html", page(plist_html, "Products", "Browse all products", f"{site.get('url','')}/products/index.html"))

    # Each product page
    ptpl = load_tpl("product.html")
    for p in products:
        content = render(ptpl, {"site": site, "product": p})
        write_out(f"products/{p['slug']}.html", page(content, p["title"], p["description"], f"{site.get('url','')}/products/{p['slug']}.html"))

    # Blog index + posts
    blog_idx = render(load_tpl("blog_index.html"), {"site": site, "posts": posts})
    write_out("blog/index.html", page(blog_idx, "Blog", "News and updates", f"{site.get('url','')}/blog/index.html"))
    post_tpl = load_tpl("post.html")
    for a in posts:
        content = render(post_tpl, {"site": site, "post": a})
        write_out(f"blog/{a['slug']}.html", page(content, a["title"], a["summary"], f"{site.get('url','')}/blog/{a['slug']}.html"))

    # RSS + sitemap
    rss_tpl = load_tpl("rss.xml")
    rss_out = render(rss_tpl, {"site": site, "seo": seo, "posts": posts})
    write_out("rss.xml", rss_out)

    urls = [f"{site.get('url','')}/", f"{site.get('url','')}/products/index.html", f"{site.get('url','')}/blog/index.html"]
    urls += [f"{site.get('url','')}/products/{p['slug']}.html" for p in products]
    urls += [f"{site.get('url','')}/blog/{a['slug']}.html" for a in posts]
    sm_tpl = open(os.path.join(TPL, "sitemap.xml"), "r", encoding="utf-8").read()
    write_out("sitemap.xml", render(sm_tpl, {"urls": urls}))

    print(f"Build complete. Products: {len(products)} • Posts: {len(posts)}")

if __name__ == "__main__":
    main()
