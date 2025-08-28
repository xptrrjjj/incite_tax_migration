// Quick Browser Investigation for PDF Viewer
// Copy and paste these commands in your browser console (F12)

console.log("🔍 Starting PDF Viewer Investigation...");

// 1. Find all Lightning components
console.log("\n📱 Lightning Components:");
const components = document.querySelectorAll('[data-aura-class], [data-lwc-class]');
components.forEach((el, i) => {
    const auraClass = el.getAttribute('data-aura-class');
    const lwcClass = el.getAttribute('data-lwc-class');
    if (auraClass && (auraClass.includes('pdf') || auraClass.includes('viewer') || auraClass.includes('document'))) {
        console.log(`${i+1}. Aura Component: ${auraClass}`);
    }
    if (lwcClass && (lwcClass.includes('pdf') || lwcClass.includes('viewer') || lwcClass.includes('document'))) {
        console.log(`${i+1}. LWC Component: ${lwcClass}`);
    }
});

// 2. Find iframes (common for PDF viewers)
console.log("\n🖼️  iFrames:");
const iframes = document.querySelectorAll('iframe');
iframes.forEach((iframe, i) => {
    console.log(`${i+1}. ${iframe.src}`);
    console.log(`   Title: ${iframe.title || 'No title'}`);
    console.log(`   Class: ${iframe.className || 'No class'}`);
});

// 3. Find scripts related to PDF
console.log("\n📜 PDF-related Scripts:");
const scripts = Array.from(document.scripts);
const pdfScripts = scripts.filter(script => 
    script.src && (
        script.src.includes('pdf') || 
        script.src.includes('viewer') || 
        script.src.includes('document') ||
        script.src.includes('static')
    )
);
pdfScripts.forEach((script, i) => {
    console.log(`${i+1}. ${script.src}`);
});

// 4. Look for PDF.js or other PDF libraries
console.log("\n📚 PDF Libraries Check:");
if (window.pdfjsLib) console.log("✓ PDF.js found");
if (window.PDFTron) console.log("✓ PDFTron found");
if (window.PSPDFKit) console.log("✓ PSPDFKit found");
if (window.Adobe) console.log("✓ Adobe SDK found");

// 5. Check for canvas elements (PDF.js uses canvas)
console.log("\n🎨 Canvas Elements:");
const canvases = document.querySelectorAll('canvas');
canvases.forEach((canvas, i) => {
    console.log(`${i+1}. Canvas: ${canvas.className || 'No class'}`);
    console.log(`   Size: ${canvas.width}x${canvas.height}`);
});

// 6. Look for specific PDF viewer indicators
console.log("\n🎯 Specific PDF Viewer Indicators:");
const pdfElements = document.querySelectorAll('[class*="pdf"], [id*="pdf"], [class*="viewer"], [id*="viewer"]');
pdfElements.forEach((el, i) => {
    console.log(`${i+1}. Element: ${el.tagName}`);
    console.log(`   Class: ${el.className}`);
    console.log(`   ID: ${el.id}`);
});

// 7. Check for annotation tools
console.log("\n✏️  Annotation Tools:");
const annotationElements = document.querySelectorAll('[class*="annotation"], [id*="annotation"], [class*="markup"], [id*="markup"]');
annotationElements.forEach((el, i) => {
    console.log(`${i+1}. ${el.tagName} - ${el.className || el.id}`);
});

console.log("\n✅ Investigation complete! Check the output above for clues.");
console.log("💡 TIP: Now go to Network tab, reload the page, and look for PDF-related requests!"); 