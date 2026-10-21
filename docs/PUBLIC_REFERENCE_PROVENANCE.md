# Public reference and provenance policy

AsterMax developers may learn from publicly accessible material found through search engines, video platforms, documentation sites, forums, conference talks, blogs, tutorials, papers, and product demonstrations. Public accessibility is **not** treated as automatic permission to copy, redistribute, adapt, or embed the material.

This document defines how public references are used safely.

## 1. Google is a discovery tool, not a license

A result found through Google or another search engine inherits the copyright, license, trademark, patent, confidentiality, and contractual status of the underlying source. Search-engine visibility does not place a work in the public domain.

Use search results to locate knowledge. Before copying code, text, images, models, drawings, data, or assets, identify the original source and its actual license or permission.

## 2. YouTube and video references

A publicly viewable video may be used to understand concepts, workflows, terminology, user expectations, demonstrations, and observable behavior. Do not assume that public viewing grants a right to extract or redistribute the video's footage, audio, screenshots, graphics, source files, downloadable assets, transcript, or proprietary implementation details.

For AsterMax, the normal safe use of a video is:

`watch / understand -> write an independent functional requirement -> design independently -> implement with original or cleared code/assets -> validate behavior`

Do not use:

`download / copy screen or asset -> reproduce source expression -> ship it`

If a creator explicitly publishes code or assets under a reusable license, record the original URL, author/project, version when available, and license before importing anything.

## 3. What may be recorded as reference evidence

For a substantial externally inspired feature, a development note or PR may record:

- source URL;
- page/video/project title;
- author/channel/publisher if known;
- date accessed;
- what functional idea was learned;
- whether any code or asset was imported;
- license/permission if anything was imported;
- the AsterMax files implementing the independently designed feature.

A URL is evidence of where an idea was observed; it is **not** evidence that copying was permitted.

## 4. Functional knowledge versus protected expression

AsterMax may learn from publicly demonstrated engineering workflows and then implement the underlying functional concept independently. Examples include:

- a feature tree for parametric modeling;
- sketch constraints;
- extrusion, revolution, fillet and pattern operations;
- assembly relationships;
- a model hierarchy for materials, interactions, mesh, loads and results;
- result contours, deformation review and reaction extraction.

Do not copy the particular expressive material used to demonstrate those concepts, such as proprietary icon artwork, exact screenshots, manual text, tutorial narration, distinctive branded layouts, sample models, or source code without a compatible license.

## 5. Code found on the public internet

Before incorporating public code, determine the license. Rules:

- compatible open-source license identified -> use only under its conditions and preserve required notices;
- explicit permission from the rights holder -> preserve the permission record;
- public-domain/CC0 material with reliable provenance -> record the source;
- no license, unclear license, copied forum snippet of uncertain origin, or repost -> do not incorporate into production source unless a legal exception or permission is documented.

When practical, rewrite the functionality independently from the behavioral requirement instead of copying uncertain code.

## 6. Screenshots, UI references and videos

Screenshots or video frames from proprietary products may be used privately as short-lived reference material where lawful, but should not be committed to the AsterMax repository, documentation, website, installer, test assets, or marketing without clearance. Describe UI requirements textually instead.

Example:

**Preferred:** "Keep the feature history visible and allow context actions on each operation."

**Avoid:** "Reproduce this vendor screen exactly," accompanied by proprietary screenshots committed to the repository.

## 7. Benchmark and tutorial models

If a tutorial teaches a mechanical problem, reproduce the **engineering problem** using an AsterMax-created model whenever possible rather than redistributing the tutorial's proprietary CAD file, screenshots, narration, or documentation. Prefer analytical benchmarks, published standards, academic benchmarks, or original models.

## 8. Historical work already performed

The fact that earlier development knowledge came from Google, YouTube, public documentation, ordinary product use, forums, or other public resources does not by itself imply infringement. Going forward, uncertain historical inputs should be handled conservatively:

1. do not claim that public availability equals permission;
2. identify any third-party code/assets actually present in the repository;
3. replace or remove material whose provenance/license cannot be established;
4. document independent AsterMax implementation where the source was only conceptual or behavioral;
5. retain lawful upstream attribution and license obligations.

## 9. Evidence standard

The strongest AsterMax provenance record is not a statement that "everything was on the internet." It is a traceable history showing:

`public/engineering reference -> functional requirement -> independent design -> original/cleared implementation -> validation`

That is the standard this repository will use.

## 10. No legal immunity claim

This policy is a risk-control and provenance practice, not a guarantee against disputes and not a substitute for jurisdiction-specific legal advice when a major commercial release, patent-sensitive feature, acquisition, investment, or litigation risk justifies counsel review.
