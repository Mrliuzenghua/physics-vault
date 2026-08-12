// 高中物理 Typst 课堂课件模板
// 画布：16:9；输出：PDF 幻灯片；公式：Typst 原生数学排版。
// 本文件不依赖在线包，适合离线课堂。

#let slide-width = 320mm
#let slide-height = 180mm
#let navy = rgb("#14213D")
#let blue = rgb("#1F5FBF")
#let blue-soft = rgb("#EAF2FF")
#let green = rgb("#167A55")
#let green-soft = rgb("#EAF7F1")
#let orange = rgb("#EF7D32")
#let ink = rgb("#172033")
#let muted = rgb("#667085")
#let line-color = rgb("#D9E2F1")
#let paper = rgb("#F7F9FC")

#set document(date: none)
#set page(width: slide-width, height: slide-height, margin: 0mm, fill: paper)
#set text(font: ("Microsoft YaHei", "SimHei"), size: 18pt, lang: "zh", fill: ink)
#set par(leading: 0.72em)

#let slide-footer(chapter, tone: blue) = context {
  let page-number = counter(page).get().first()
  let page-label = if page-number < 10 { "0" + str(page-number) } else { str(page-number) }
  grid(
    columns: (1fr, auto),
    align: horizon,
    [#set text(size: 10pt, fill: muted); #chapter],
    [#set text(size: 12pt, weight: "bold", fill: tone); #page-label],
  )
}

#let slide-shell(chapter, tone: blue, fill: paper, body) = block(
  width: 100%, height: 100%, fill: fill,
  inset: (x: 14mm, top: 10mm, bottom: 7mm),
)[
  #grid(
    rows: (1fr, auto),
    row-gutter: 2mm,
    body,
    slide-footer(chapter, tone: tone),
  )
]

#let pill(body, tone: blue, background: blue-soft) = box(
  fill: background, radius: 3mm, inset: (x: 5mm, y: 2mm),
)[#set text(size: 12pt, weight: "bold", fill: tone); #body]

#let card(body, fill: white, stroke: line-color, radius: 3mm, inset: 6mm) = block(
  width: 100%, fill: fill, stroke: 0.7pt + stroke, radius: radius, inset: inset,
)[#body]

#let cover-slide(title, subtitle, grade, lesson-type, teacher, school, question-count) = block(
  width: 100%, height: 100%, fill: navy,
)[
  #grid(
    columns: (5mm, 1fr),
    rect(width: 5mm, height: 100%, fill: orange),
    block(inset: (left: 14mm, right: 16mm, top: 14mm, bottom: 10mm))[
      #grid(
        rows: (auto, 1fr, auto),
        [#set text(size: 13pt, weight: "bold", fill: rgb("#B8D4FF")); 高中物理 · Typst 课堂课件],
        align(horizon)[
          #set text(fill: white)
          #text(size: 42pt, weight: "bold")[#title]
          #v(5mm)
          #text(size: 22pt, fill: rgb("#D8E4F5"))[#subtitle]
        ],
        grid(
          columns: (1fr, auto), align: bottom,
          [
            #set text(size: 15pt, fill: rgb("#B8C5D9"))
            #grade　·　#lesson-type　·　#teacher
            #v(8mm)
            #text(size: 10pt, fill: rgb("#94A3B8"))[#school]
          ],
          [#set text(size: 18pt, weight: "bold", fill: orange); #question-count 道题],
        ),
      )
    ],
  )
]

#let image-panel(paths) = {
  let columns = if paths.len() == 1 { (1fr,) } else { (1fr, 1fr) }
  grid(
    columns: columns,
    column-gutter: 3mm,
    row-gutter: 3mm,
    ..paths.map(path => card(inset: 3mm)[#image(path, width: 100%, height: 100%, fit: "contain")]),
  )
}

#let choices-panel(choices) = {
  let labels = ("A", "B", "C", "D", "E", "F", "G", "H")
  for (index, choice) in choices.enumerate() {
    block(
      width: 100%, fill: white, stroke: 0.6pt + line-color, radius: 2.4mm,
      inset: (x: 5mm, y: 2.8mm),
    )[
      #set text(size: 17pt)
      #text(weight: "bold")[#(labels.at(index) + ".")] #h(2mm) #choice
    ]
    v(2mm)
  }
}

#let question-slide(number, kind, title, source-label, chapter, stem, choices: (), data: (), prompt: [], image-paths: ()) = slide-shell(chapter)[
  #grid(
    rows: (auto, auto, 1fr),
    row-gutter: 4mm,
    grid(
      columns: (auto, 1fr, auto), align: horizon, column-gutter: 5mm,
      pill(kind),
      [#set text(size: 28pt, weight: "bold"); #title],
      [#set text(size: 11pt, fill: muted); #source-label],
    ),
    line(length: 100%, stroke: 1.2pt + blue),
    if image-paths.len() > 0 {
      grid(
        columns: (2.15fr, 0.85fr), column-gutter: 8mm,
        grid(
          rows: (auto, auto, 1fr), row-gutter: 3mm,
          card()[#set text(size: 18pt); #stem],
          if data.len() > 0 {
            block(width: 100%, fill: blue-soft, radius: 2.5mm, inset: (x: 4mm, y: 2.6mm))[
              #set text(size: 15pt, weight: "bold", fill: blue)
              #grid(columns: data.map(_ => 1fr), column-gutter: 3mm, ..data.map(item => align(center)[#item]))
            ]
          } else { [] },
          if choices.len() > 0 { choices-panel(choices) } else { card(fill: paper)[#set text(size: 17pt); #prompt] },
        ),
        image-panel(image-paths),
      )
    } else {
      grid(
        rows: (auto, auto, 1fr), row-gutter: 3mm,
        card()[#set text(size: 18pt); #stem],
        if data.len() > 0 {
          block(width: 100%, fill: blue-soft, radius: 2.5mm, inset: (x: 4mm, y: 2.6mm))[
            #set text(size: 15pt, weight: "bold", fill: blue)
            #grid(columns: data.map(_ => 1fr), column-gutter: 3mm, ..data.map(item => align(center)[#item]))
          ]
        } else { [] },
        if choices.len() > 0 { choices-panel(choices) } else { card(fill: paper)[#set text(size: 18pt); #prompt] },
      )
    },
  )
]

#let answer-slide(number, title, chapter, answer, analysis, keypoint, recall) = slide-shell(chapter, tone: green, fill: white)[
  #grid(
    rows: (auto, auto, 1fr), row-gutter: 4mm,
    [#set text(size: 13pt, weight: "bold", fill: green); 第 #number 题 · 解析],
    [#set text(size: 28pt, weight: "bold"); #title],
    grid(
      columns: (0.95fr, 2fr), column-gutter: 8mm,
      grid(
        rows: (auto, 1fr), row-gutter: 5mm,
        block(width: 100%, fill: green-soft, radius: 3mm, inset: 6mm)[
          #set text(size: 20pt, weight: "bold", fill: green)
          答案　#answer
        ],
        card(fill: paper)[
          #set text(size: 12pt, fill: muted)
          #text(weight: "bold")[题意回顾]
          #v(2mm)
          #recall
        ],
      ),
      grid(
        rows: (1fr, auto), row-gutter: 5mm,
        card(fill: paper)[
          #set text(size: 17pt)
          #for (index, item) in analysis.enumerate() {
            block(width: 100%)[#text(weight: "bold")[#(str(index + 1) + ".")] #h(2mm) #item]
            v(3mm)
          }
        ],
        if keypoint != [] {
          block(width: 100%, fill: rgb("#FFF7ED"), stroke: 1.2pt + orange, radius: 3mm, inset: (x: 6mm, y: 4mm))[
            #set text(size: 15pt)
            *易错提醒：* #keypoint
          ]
        } else { [] },
      ),
    ),
  )
]

#let closing-slide(chapter, question-count) = slide-shell(chapter)[
  #align(horizon)[
    #set text(fill: ink)
    #text(size: 15pt, weight: "bold", fill: blue)[课堂回顾]
    #v(8mm)
    #text(size: 36pt, weight: "bold")[把过程讲清，比记住答案更重要]
    #v(14mm)
    #text(size: 20pt, weight: "bold", fill: muted)[本节完成 #question-count 道题]
    #v(5mm)
    #text(size: 17pt, fill: muted)[请回看每道题的研究对象、过程划分、规律选择与单位检查。]
    #v(12mm)
    #line(length: 42mm, stroke: 3pt + orange)
    #v(8mm)
    #text(size: 18pt, weight: "bold", fill: blue)[课后任务：独立复述关键步骤，再完成同类变式。]
  ]
]

// {{GENERATED_CONTENT}}
