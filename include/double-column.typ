#let render-double-column(data) = {
  // Document settings
  set document(title: data.title, author: data.authors.map(a => a.name))
  set page(paper: "a4", margin: 1in)
  set text(font: "New Computer Modern", size: 10pt)
  set par(justify: true, leading: 0.55em)
  set heading(numbering: "1.1.")
  set math.equation(numbering: "(1)")

  // Helper function to replace @IDs with dynamic numbers
  let process-text(text-str) = {
    let resolved-str = text-str
    if "references" in data {
      let i = 1
      for ref in data.references {
        resolved-str = resolved-str.replace("@" + ref.id, str(i))
        i += 1
      }
    }
    eval(resolved-str, mode: "markup")
  }

  // Title and Authors (spanning both columns)
  align(center)[
    #block(text(weight: "bold", size: 17pt, eval(data.title, mode: "markup")))
    #v(1em)
    #let authors = data.authors
    #let row-size = 3
    #let rows = range(0, calc.ceil(authors.len() / row-size))
    #for row in rows {
      let start = row * row-size
      let end = calc.min(start + row-size, authors.len())
      let group = authors.slice(start, end)
      grid(
        columns: group.len(),
        gutter: 1.5em,
        ..group.map(a => align(center)[
          #text(weight: "bold", eval(a.name, mode: "markup")) \
          #text(size: 9pt, eval(a.affiliation, mode: "markup"))
        ])
      )
      v(0.5em)
    }
  ]
  v(1em)

  // Start two-column layout for the body content
  show: columns.with(2, gutter: 1.5em)

  // Abstract (inside two-column layout)
  if "abstract" in data {
    align(center)[*Abstract*]
    v(0.3em)
    eval(data.abstract, mode: "markup")
    v(1.5em)
  }

  // ---------------------------------------------------------
  // THE RECURSIVE ENGINE
  // ---------------------------------------------------------
  let render-blocks(blocks) = {
    for item in blocks {
      if item.type == "section" {
        heading(level: 1)[#eval(item.title, mode: "markup")]
        if "content" in item { render-blocks(item.content) }
      } else if item.type == "subsection" {
        heading(level: 2)[#eval(item.title, mode: "markup")]
        if "content" in item { render-blocks(item.content) }
      } else if item.type == "subsubsection" {
        heading(level: 3)[#eval(item.title, mode: "markup")]
        if "content" in item { render-blocks(item.content) }
      } else if item.type == "paragraph" {
        process-text(item.text)
      } else if item.type == "equation" {
        math.equation(block: true, eval(item.math, mode: "math"))
      } else if item.type == "image" {
        let img-width = auto
        if "width" in item { img-width = eval(item.width) }
        let img-caption = none
        if "caption" in item { img-caption = eval(item.caption, mode: "markup") }
        figure(image(item.src, width: img-width), caption: img-caption)
      } else if item.type == "table" {
        let table-cells = ()
        if "headers" in item {
          for h in item.headers { table-cells.push([*#eval(h, mode: "markup")*]) }
        }
        if "data" in item {
          for row in item.data {
            for cell in row { table-cells.push(eval(cell, mode: "markup")) }
          }
        }
        let t = table(columns: item.columns, align: center + horizon, ..table-cells)
        if "caption" in item {
          figure(t, caption: eval(item.caption, mode: "markup"), kind: table)
        } else { t }
      }
    }
  }

  if "content" in data {
    render-blocks(data.content)
  }

  // ---------------------------------------------------------
  // REFERENCES
  // ---------------------------------------------------------
  if "references" in data and data.references.len() > 0 {
    v(1.5em)
    heading(level: 1, numbering: none)[References]
    let i = 1
    for ref in data.references {
    let citation_str = ""
    if "authors" in ref { citation_str += ref.authors + ". " }
    if "title" in ref { citation_str += "\"" + ref.title + "\" " }
    if "journal" in ref { citation_str += "_" + ref.journal + "_. " }
    if "volume" in ref { citation_str += ref.volume }
    if "pages" in ref { citation_str += ", pp. " + ref.pages }
    if "year" in ref { citation_str += " (" + ref.year + ")" }
    citation_str += "."
    block[
      [#i] #eval(citation_str, mode: "markup")
    ]
    i += 1
  }
  }
}

#let json-file-path = sys.inputs.at("json_path", default: "paper.json")
#let paper-data = json(json-file-path)
#render-double-column(paper-data)
