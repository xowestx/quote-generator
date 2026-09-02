/**
 * -----------------------------------------------------------------------
 * COMBINED AUTOMATION SYSTEM - FINAL SINGLE-SOURCE VERSION
 * 1. ORGANIZER: Takes Form responses -> Expands them -> Puts in "Organized Data"
 * 2. GENERATOR: Takes "Organized Data" -> Generates Google Doc -> Logs it
 * 3. WEBHOOK: Listens for Streamlit to generate docs remotely (Supports PDF Conversions & Python Merges)
 * -----------------------------------------------------------------------
 */

// ==========================================
// CONFIGURATION & CONSTANTS
// ==========================================

const CONFIG = {
  // URLs
  CLIENT_SHEET_URL: "https://docs.google.com/spreadsheets/d/1yYL2qT6AfwcxbwpFzZRyS8DjgrLh8ScP9n52r_-H4Hs/edit?usp=sharing",
  // APP is the single source for products, rates, and Terms & Conditions.
  TERMS_SHEET_URL:  "https://docs.google.com/spreadsheets/d/1uyZXYMvaeuH-ZQOxHgpdyXiC2vlvUHtK3Cmde63cnUY/edit?usp=sharing",
  LOG_SHEET_URL:    "https://docs.google.com/spreadsheets/d/1KzC5U2_70r_eczYa4aW5VMRkAQO1TCbjDWfNThfNwVE/edit?usp=sharing",
  
  // Default IDs & Names
  DESTINATION_FOLDER_ID: "10FDn5lDAjOfLMIT8oOZwlj0pFlBZnRE4", 
  PDF_DESTINATION_FOLDER_ID: "1Iz02maH0SEDjcUCP2fRDUYs25T-58FHG", 
  TEMPLATE_ID:           "1ZWJPsNMztWqh0lXpo8V0cPYX-MFuBHx2sQXXpq2TEhI",
  LAND_EXTENSION_TEMPLATE_ID: "1tveP5rAcdIDLAfg5wiO2DLrqYRGoMyecV8qRZZYzYDQ", 
  
  // Bedroom/Furniture Specific IDs
  FURNITURE_TEMPLATE_ID: "1YNzIbo-Kikmgq69KpbfFfU2eq_mzpw7YBnzIpBcF55k",
  FURNITURE_DOC_FOLDER_ID: "1aJAs9S4tPoLaZbP2A2V6iVxtnAvTSW2J",
  FURNITURE_PDF_FOLDER_ID: "11OQX4eAL6ExSM-EwWgipLy5Gi1qIstr1",
  
  // Tab Names
  TARGET_SHEET_NAME:     "Organized Data",
  LOG_TAB_NAME:          "Quotation Log",
  CLIENT_SHEET_TAB:      "Sheet1",
  TERMS_SHEET_TAB:       "TERMS & CONDITIONS",
  
  // Design
  FONT_FAMILY: "Century Gothic",
  FIXED_ITEM_COUNT: 20, // 20 Slots for items

  // Land Extension pricing is selected in Streamlit. Apps Script accepts only
  // these approved rates and never substitutes its own fixed value.
  LAND_EXTENSION_ALLOWED_RATES: [55000, 65000]
};

// ==========================================
// 1. MENU & TRIGGER SETUP
// ==========================================

function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('🚀 Automation Hub')
      .addItem('🔑 Authorize Drive (Fix PDF Permissions)', 'authorizeDrive')
      .addItem('✅ Initialize System (Click Once)', 'setupTrigger')
      .addSeparator()
      .addItem('🔄 Force Run: Organize & Generate Pending', 'manualForceRun')
      .addItem('🎯 Generate Quote for Selected Row', 'manualRunSelectedRow')
      .addItem('⚠️ Reset Quote Counter', 'resetQuoteCounter')
      .addToUi();
}

/**
 * Run this once to grant the script permission to manage Drive files 
 * (Fixes "Access denied" errors during PDF generation from Streamlit).
 */
function authorizeDrive() {
  try {
    // Forcing Google to register full Drive scopes by accessing the root folder
    const rootFolder = DriveApp.getRootFolder();
    const folderName = rootFolder.getName();
    
    SpreadsheetApp.getUi().alert(
      "✅ Drive Permissions Authorized!\n\n" +
      "The script successfully accessed Drive.\n\n" +
      "⚠️ CRITICAL NEXT STEP ⚠️\n" +
      "You MUST go to Deploy -> Manage Deployments -> Edit -> select 'New version' -> Deploy. " +
      "If you do not deploy a NEW version, Streamlit will keep getting the Access Denied error!"
    );
  } catch(e) {
    console.error("Authorization failed: ", e);
    SpreadsheetApp.getUi().alert("❌ Authorization failed. Please run again and accept permissions.");
  }
}

function setupTrigger() {
  const ss = SpreadsheetApp.getActive();
  const triggers = ScriptApp.getProjectTriggers();
  
  // Remove old triggers to prevent double firing
  triggers.forEach(t => ScriptApp.deleteTrigger(t));
  
  // Create NEW Unified Trigger
  ScriptApp.newTrigger('mainPipeline')
    .forSpreadsheet(ss)
    .onFormSubmit()
    .create();
    
  SpreadsheetApp.getUi().alert('✅ System Initialized! \n\nWhen a Form is submitted, the data will be organized AND the Google Doc will be generated automatically.');
}

// ==========================================
// 2. MAIN PIPELINE (THE ORCHESTRATOR)
// ==========================================

function mainPipeline(e) {
  if (!e || !e.range) {
    console.warn("mainPipeline was run without an event object. This is normal if run manually.");
  }
  
  console.log("--- STARTING PIPELINE ---");
  const result = organizeFormResponses(e);
  if (result && result.sheet) {
    processPendingRows(result.sheet, result.rowIndex);
  }
  console.log("--- PIPELINE COMPLETE ---");
}

function manualForceRun() {
  mainPipeline(null);
  SpreadsheetApp.getUi().alert("Manual Run Complete.");
}

function manualRunSelectedRow() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const activeSheet = ss.getActiveSheet();
  const activeCell = activeSheet.getActiveCell();
  const activeRow = activeCell.getRow();
  const ui = SpreadsheetApp.getUi();

  if (activeRow < 2) {
    ui.alert("⚠️ Please select a valid data row (Row 2 or below).");
    return;
  }

  if (activeSheet.getName() === CONFIG.TARGET_SHEET_NAME) {
    const headers = activeSheet.getRange(1, 1, 1, activeSheet.getLastColumn()).getValues()[0];
    const colUrl = headers.indexOf("Generated Doc URL");
    
    if (colUrl === -1) {
      ui.alert("⚠️ Could not find 'Generated Doc URL' column.");
      return;
    }

    const currentUrl = activeSheet.getRange(activeRow, colUrl + 1).getValue();

    if (currentUrl && currentUrl.toString().trim() !== "") {
      const response = ui.alert(
        "Document Already Exists", 
        "This row already has a generated document. Do you want to generate a NEW one and overwrite the URL?", 
        ui.ButtonSet.YES_NO
      );
      if (response === ui.Button.YES) {
        activeSheet.getRange(activeRow, colUrl + 1).clearContent();
        processPendingRows(activeSheet, activeRow);
        ui.alert("✅ New Quotation Generated for Organized Data Row " + activeRow);
      }
    } else {
      processPendingRows(activeSheet, activeRow);
      ui.alert("✅ Quotation Generated for Organized Data Row " + activeRow);
    }
  } else {
    const response = ui.alert(
      "Process Raw Row", 
      "You have selected Row " + activeRow + " in the raw form responses. This will organize the row and immediately generate a quote. Continue?", 
      ui.ButtonSet.YES_NO
    );
    
    if (response === ui.Button.YES) {
      const mockEvent = {
        range: activeSheet.getRange(activeRow, 1) 
      };
      mainPipeline(mockEvent);
      ui.alert("✅ Row " + activeRow + " has been organized and a quote was generated!");
    }
  }
}

// ==========================================
// 3. STEP 1: ORGANIZE FORM DATA
// ==========================================

function organizeFormResponses(e) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sourceSheet;
  if (e && e.range) {
    sourceSheet = e.range.getSheet();
  } else {
    const sheets = ss.getSheets();
    sourceSheet = sheets.find(s => {
      const h = s.getRange(1, 1, 1, 5).getValues()[0];
      return h.includes('Timestamp') && h.includes('ZONE?');
    });
    if (!sourceSheet) sourceSheet = ss.getActiveSheet();
  }

  const lastCol = sourceSheet.getLastColumn();
  const headers = sourceSheet.getRange(1, 1, 1, lastCol).getValues()[0];

  const colMap = {
    timestamp: headers.indexOf("Timestamp"),
    zone: headers.indexOf("ZONE?"),
    request: headers.indexOf("REQUEST"),
    unitIds: [],
    startOfItems: headers.findIndex(h => h && h.toString().trim() === "Description")
  };
  
  headers.forEach((h, i) => {
    if (h && h.toString().toUpperCase().includes("UNIT ID")) colMap.unitIds.push(i);
  });

  if (colMap.startOfItems === -1) {
    console.error("Could not find 'Description' column");
    return null;
  }

  let targetSheet = ss.getSheetByName(CONFIG.TARGET_SHEET_NAME);
  if (!targetSheet) {
    targetSheet = ss.insertSheet(CONFIG.TARGET_SHEET_NAME);
    const headerRow = ["Timestamp", "ZONE?", "REQUEST", "UNIT ID"];
    for (let k = 0; k < CONFIG.FIXED_ITEM_COUNT; k++) headerRow.push("Description", "Unit", "QTY", "Rate");
    headerRow.push("Generated Doc URL", "Quotation ID");
    targetSheet.appendRow(headerRow);
    targetSheet.getRange(1, 1, 1, headerRow.length).setFontWeight("bold").setBackground("#efefef");
  }

  if (e && e.range) {
    console.log("Running in Single-Row Event Mode");
    const rowData = sourceSheet.getRange(e.range.getRow(), 1, 1, lastCol).getValues()[0];
    const processedRow = processSingleRow(rowData, colMap);
    
    const finalRow = [...processedRow.meta];
    for (let i = 0; i < CONFIG.FIXED_ITEM_COUNT; i++) {
      if (i < processedRow.items.length) finalRow.push(...processedRow.items[i]);
      else finalRow.push("", "", "", "");
    }
    finalRow.push("", "");
    
    targetSheet.appendRow(finalRow);
    const newRowIndex = targetSheet.getLastRow();
    targetSheet.getRange(newRowIndex, 1, 1, finalRow.length).setBorder(true, true, true, true, true, true, '#d9d9d9', SpreadsheetApp.BorderStyle.SOLID);
    return { sheet: targetSheet, rowIndex: newRowIndex };
  }

  console.log("Running in Full Sync Manual Mode");
  const data = sourceSheet.getDataRange().getValues();
  if (data.length < 1) return null;

  const existingDataMap = new Map();
  if (targetSheet.getLastRow() > 1) {
    const tData = targetSheet.getDataRange().getValues();
    const tHeaders = tData[0];
    const urlIdx = tHeaders.indexOf("Generated Doc URL");
    const idIdx = tHeaders.indexOf("Quotation ID");
    
    if (urlIdx > -1 && idIdx > -1) {
      for (let i = 1; i < tData.length; i++) {
        const key = `${tData[i][0]}_${tData[i][3]}`; 
        existingDataMap.set(key, { url: tData[i][urlIdx], id: tData[i][idIdx] });
      }
    }
  }

  const finalData = [];
  const headerRow = ["Timestamp", "ZONE?", "REQUEST", "UNIT ID"];
  for (let k = 0; k < CONFIG.FIXED_ITEM_COUNT; k++) headerRow.push("Description", "Unit", "QTY", "Rate");
  headerRow.push("Generated Doc URL", "Quotation ID");
  finalData.push(headerRow);

  for (let i = 1; i < data.length; i++) {
    const rowObj = processSingleRow(data[i], colMap);
    const currentRow = [...rowObj.meta];
    
    for (let k = 0; k < CONFIG.FIXED_ITEM_COUNT; k++) {
      if (k < rowObj.items.length) currentRow.push(...rowObj.items[k]);
      else currentRow.push("", "", "", "");
    }

    const key = `${rowObj.meta[0]}_${rowObj.meta[3]}`;
    const saved = existingDataMap.get(key);
    if (saved) currentRow.push(saved.url, saved.id);
    else currentRow.push("", "");

    finalData.push(currentRow);
  }

  targetSheet.clear();
  if (finalData.length > 0) {
    const range = targetSheet.getRange(1, 1, finalData.length, finalData[0].length);
    range.setValues(finalData);
    targetSheet.getRange(1, 1, 1, finalData[0].length).setFontWeight("bold").setBackground("#efefef");
    range.setBorder(true, true, true, true, true, true, '#d9d9d9', SpreadsheetApp.BorderStyle.SOLID);
    targetSheet.autoResizeColumns(1, finalData[0].length);
  }

  return { sheet: targetSheet, rowIndex: null };
}

function processSingleRow(row, colMap) {
  const timestamp = colMap.timestamp > -1 ? row[colMap.timestamp] : "";
  const zone = colMap.zone > -1 ? row[colMap.zone] : "";
  const request = colMap.request > -1 ? row[colMap.request] : "";
  
  let unitId = "";
  for (let uIndex of colMap.unitIds) {
    if (row[uIndex] && row[uIndex].toString().trim() !== "") {
      unitId = row[uIndex];
      break;
    }
  }

  const currentItems = [];
  const blockSize = 5; 
  for (let j = colMap.startOfItems; j < row.length; j += blockSize) {
    if (j + 3 >= row.length) break;
    const desc = row[j];
    const unit = row[j+1];
    const qty = row[j+2];
    const rate = row[j+3];

    if (desc && desc.toString().trim() !== "") {
      currentItems.push([desc, unit, qty, rate]);
    }
  }

  return {
    meta: [timestamp, zone, request, unitId],
    items: currentItems
  };
}

// ==========================================
// 4. STEP 2: GENERATE DOCS (SHEET METHOD)
// ==========================================

function processPendingRows(sheet, specificRowIndex) {
  if (!sheet) return;
  
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const colUrl = headers.indexOf("Generated Doc URL");
  const colId = headers.indexOf("Quotation ID");
  
  if (colUrl === -1 || colId === -1) {
    console.error("Critical columns missing in Organized Data");
    return;
  }

  if (specificRowIndex) {
    console.log(`Processing Specific Row: ${specificRowIndex}`);
    const rowValues = sheet.getRange(specificRowIndex, 1, 1, sheet.getLastColumn()).getValues()[0];
    const currentUrl = rowValues[colUrl];
    const unitId = rowValues[3];
    
    if ((!currentUrl || currentUrl === "") && unitId) {
      generateQuoteForRow(sheet, specificRowIndex, rowValues, colUrl + 1, colId + 1);
    }
    return;
  }

  console.log("Scanning all rows for pending quotes...");
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return;
  
  const data = sheet.getDataRange().getValues();
  for (let i = 1; i < data.length; i++) {
    const row = data[i];
    const currentUrl = row[colUrl];
    const unitId = row[3];
    
    if ((!currentUrl || currentUrl === "") && unitId) {
      console.log(`Generating Quote for Row ${i + 1}`);
      try {
        generateQuoteForRow(sheet, i + 1, row, colUrl + 1, colId + 1);
      } catch (err) {
        console.error(`Error processing row ${i+1}: ${err.toString()}`);
      }
    }
  }
}

function generateQuoteForRow(sheet, rowIndex, rowData, urlColIndex, idColIndex) {
  const formData = {
    timestamp: rowData[0],
    zone: rowData[1],
    requestType: rowData[2],
    unitId: rowData[3]
  };

  const items = [];
  const startCol = 4;
  const itemBlock = 4;
  
  for (let k = 0; k < CONFIG.FIXED_ITEM_COUNT; k++) {
    const base = startCol + (k * itemBlock);
    if (base >= rowData.length) break;
    
    const desc = rowData[base];
    const unit = rowData[base+1];
    const qty = rowData[base+2];
    const rate = rowData[base+3];
    
    if (desc && desc.toString().trim() !== "") {
      items.push({
        description: desc,
        unit: unit,
        qty: qty,
        rate: Number(rate),
        total: (Number(qty) || 0) * (Number(rate) || 0)
      });
    }
  }

  if (items.length === 0) {
    console.log("No items found for this row.");
    return;
  }

  const serialNumber = getUniqueSerialNumber();
  const clientName = getClientName(formData.unitId);
  const termsText = getTermsAndConditions(formData.requestType);
  const docName = `${formData.unitId} - ${serialNumber} - ${formData.requestType}`;

  let subTotal = 0;
  items.forEach(item => { subTotal += item.total; });

  const reqTypeStr = formData.requestType ? formData.requestType.toString().toUpperCase().trim() : "";
  const isLandExtension = reqTypeStr.includes("LAND EXTENSION");
  
  // Checking if the request starts with a number followed by "BEDROOM"
  const isBedroomPackage = /^\d+\s+BEDROOM/.test(reqTypeStr);

  const vatRate = isLandExtension ? 0.0 : 0.14;
  const vatAmount = subTotal * vatRate;
  const grandTotal = subTotal + vatAmount;

  const moneyWords = isLandExtension 
    ? `Only ${convertNumberToWords(grandTotal)} Egyptian Pound & Zero Piaster`
    : `Only ${convertNumberToWords(grandTotal)} Egyptian Pound & ${Math.round((grandTotal - Math.floor(grandTotal)) * 100)}/100 Piaster`;

  // Dynamic Template & Folder Selection
  let templateId = CONFIG.TEMPLATE_ID;
  if (isLandExtension) templateId = CONFIG.LAND_EXTENSION_TEMPLATE_ID;
  if (isBedroomPackage) templateId = CONFIG.FURNITURE_TEMPLATE_ID;
  
  const destFolderId = isBedroomPackage ? CONFIG.FURNITURE_DOC_FOLDER_ID : CONFIG.DESTINATION_FOLDER_ID;

  const templateFile = DriveApp.getFileById(templateId);
  const destinationFolder = DriveApp.getFolderById(destFolderId);
  const copy = templateFile.makeCopy(docName, destinationFolder);
  const doc = DocumentApp.openById(copy.getId());
  const body = doc.getBody();

  const formattedDate = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "dd-MMM-yyyy");
  
  body.replaceText("{{unit}}", formData.unitId || "");
  body.replaceText("{{client}}", clientName || "");
  body.replaceText("{{zone}}", formData.zone || "");
  body.replaceText("{{request}}", formData.requestType || "");
  body.replaceText("{{date}}", formattedDate);
  body.replaceText("{{number}}", serialNumber);
  
  body.replaceText("{{subtotal}}", Number(subTotal).toLocaleString('en-US', {minimumFractionDigits: 2}));
  body.replaceText("{{vat}}", Number(vatAmount).toLocaleString('en-US', {minimumFractionDigits: 2}));
  body.replaceText("{{total}}", Number(grandTotal).toLocaleString('en-US', {minimumFractionDigits: 2}));
  body.replaceText("{{word}}", moneyWords);

  const termsRange = body.findText("{{terms}}");
  if (termsRange) {
    const element = termsRange.getElement();
    const parentPara = element.getParent();
    const index = body.getChildIndex(parentPara);
    body.removeChild(parentPara);
    
    if (termsText) {
      const termLines = termsText.toString().split('\n');
      termLines.reverse().forEach(line => { 
        if(line.trim() !== "") {
          body.insertListItem(index, line.trim())
              .setGlyphType(DocumentApp.GlyphType.BULLET)
              .setFontFamily(CONFIG.FONT_FAMILY)
              .setFontSize(9)
              .setBold(false);
        }
      });
    }
  }

  const searchResult = body.findText("{{table}}");
  if (searchResult) {
    const element = searchResult.getElement();
    const parent = element.getParent();
    const index = body.getChildIndex(parent);
    body.removeChild(parent); 
    
    if (items.length > 0) {
      const tableHeader = [["No.", "Description", "Unit", "QTY", "Rate", "Total Amount"]];
      const tableRows = items.map((item, idx) => [
        String(idx + 1),
        String(item.description),
        String(item.unit),
        String(item.qty),
        Number(item.rate).toLocaleString('en-US', {minimumFractionDigits: 2}),
        Number(item.total).toLocaleString('en-US', {minimumFractionDigits: 2})
      ]);
      
      const table = body.insertTable(index, tableHeader.concat(tableRows));
      
      table.setAttributes({ 
        [DocumentApp.Attribute.FONT_FAMILY]: CONFIG.FONT_FAMILY,
        [DocumentApp.Attribute.FONT_SIZE]: 10,
        [DocumentApp.Attribute.INDENT_START]: -36 
      });

      for (let r = 0; r < table.getNumRows(); r++) {
        const row = table.getRow(r);
        for (let c = 0; c < row.getNumCells(); c++) {
          const cell = row.getCell(c);
          cell.setVerticalAlignment(DocumentApp.VerticalAlignment.CENTER);
          cell.setPaddingTop(0); cell.setPaddingBottom(0); cell.setPaddingLeft(0); cell.setPaddingRight(0);

          let alignment = DocumentApp.HorizontalAlignment.CENTER;
          if (r > 0 && c === 1) {
            alignment = DocumentApp.HorizontalAlignment.LEFT;
          }

          const numChildren = cell.getNumChildren();
          for (let p = 0; p < numChildren; p++) {
            const child = cell.getChild(p);
            if (child.getType() === DocumentApp.ElementType.PARAGRAPH) {
              child.asParagraph().setAlignment(alignment);
            }
          }
        }
      }

      table.getRow(0).setAttributes({ [DocumentApp.Attribute.BOLD]: true });

      table.setColumnWidth(0, 28.8);    // No. (0.4")
      table.setColumnWidth(1, 288.0);   // Description (4.0")
      table.setColumnWidth(2, 36.0);    // Unit (0.5")
      table.setColumnWidth(3, 23.76);   // Qty (0.33")
      table.setColumnWidth(4, 72.576);  // Rate (1.008")
      table.setColumnWidth(5, 81.36);   // Total (1.13")
    }
  }

  doc.saveAndClose();
  const docUrl = doc.getUrl();

  sheet.getRange(rowIndex, urlColIndex).setValue(docUrl);
  sheet.getRange(rowIndex, idColIndex).setValue(serialNumber);

  logGeneratedQuote({
    serial: serialNumber,
    unit: formData.unitId,
    client: clientName,
    requestType: formData.requestType,
    total: grandTotal,
    zone: formData.zone
  });
}

// ==========================================
// 5. HELPER FUNCTIONS
// ==========================================

function getClientName(targetUnitId) {
  try {
    const extSS = SpreadsheetApp.openByUrl(CONFIG.CLIENT_SHEET_URL);
    const sheet = extSS.getSheetByName(CONFIG.CLIENT_SHEET_TAB);
    const data = sheet.getDataRange().getValues();
    const headers = data[0];
    const unitColIndex = headers.indexOf("Unit");
    const customerColIndex = headers.indexOf("Customer");
    
    if (unitColIndex === -1 || customerColIndex === -1) return "Client Not Found";

    for (let i = 1; i < data.length; i++) {
      if (String(data[i][unitColIndex]).trim() === String(targetUnitId).trim()) {
        return String(data[i][customerColIndex]).replace(/[\r\n]+/g, " ").trim();
      }
    }
    return "Client Not Found";
  } catch (e) { return "Error Reading Client Sheet"; }
}

function getTermsAndConditions(requestType) {
  try {
    const extSS = SpreadsheetApp.openByUrl(CONFIG.TERMS_SHEET_URL);
    const sheet = extSS.getSheetByName(CONFIG.TERMS_SHEET_TAB);
    if (!sheet) throw new Error("Terms tab not found: " + CONFIG.TERMS_SHEET_TAB);
    const data = sheet.getDataRange().getValues();
    for (let i = 1; i < data.length; i++) {
      if (String(data[i][0]).trim() === String(requestType).trim()) {
        return data[i][1]; 
      }
    }
    return "Standard Terms."; 
  } catch (e) { return "Error Reading Terms Sheet"; }
}

function logGeneratedQuote(data) {
  try {
    const ss = SpreadsheetApp.openByUrl(CONFIG.LOG_SHEET_URL);
    let sheet = ss.getSheetByName(CONFIG.LOG_TAB_NAME);
    
    if (!sheet) {
      sheet = ss.insertSheet(CONFIG.LOG_TAB_NAME);
      sheet.appendRow(["Quotation No.", "Unit ID", "Owner Name", "REQUEST", "Date", "Grand Total", "Revision", "ZONE"]);
      sheet.getRange(1, 1, 1, 8).setFontWeight("bold"); 
    }
    
    const timestamp = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "dd/MM/yyyy HH:mm:ss");
    sheet.appendRow([data.serial, data.unit, data.client, data.requestType, timestamp, data.total, "R00", data.zone]);
    
  } catch (e) {
    console.error("Error logging quote: " + e.toString());
  }
}

function getUniqueSerialNumber() {
  const props = PropertiesService.getScriptProperties();
  let counter = Number(props.getProperty('QUOTE_COUNTER')) || 0;
  counter++;
  props.setProperty('QUOTE_COUNTER', counter.toString());
  return String(counter).padStart(4, '0');
}

function resetQuoteCounter() {
  const ui = SpreadsheetApp.getUi();
  const response = ui.alert('⚠️ Reset Counter', 'Set counter to 0? Next will be #0001.', ui.ButtonSet.YES_NO);
  if (response == ui.Button.YES) {
    PropertiesService.getScriptProperties().setProperty('QUOTE_COUNTER', '0');
    ui.alert('✅ Counter reset.');
  }
}

function convertNumberToWords(amount) {
  const s = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"];
  const d = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"];
  const teens = ["Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"];
  
  const convertInteger = (n) => {
    if (n < 10) return s[n];
    if (n < 20) return teens[n - 10];
    if (n < 100) return d[Math.floor(n / 10)] + (n % 10 ? " " + s[n % 10] : "");
    if (n < 1000) return s[Math.floor(n / 100)] + " Hundred" + (n % 100 ? " " + convertInteger(n % 100) : "");
    if (n < 1000000) return convertInteger(Math.floor(n / 1000)) + " Thousand" + (n % 1000 ? " " + convertInteger(n % 1000) : "");
    if (n < 1000000000) return convertInteger(Math.floor(n / 1000000)) + " Million" + (n % 1000000 ? " " + convertInteger(n % 1000000) : "");
    return "";
  };
  return convertInteger(Math.floor(amount)) || "Zero";
}

// ==========================================
// 6. WEBHOOK LISTENER (FOR STREAMLIT UI)
// ==========================================

function appendAcDetailedScope(body, scopeItems, unitId) {
  if (!Array.isArray(scopeItems) || scopeItems.length === 0) return;

  body.appendPageBreak();
  body.appendParagraph("Detailed Scope of Work")
      .setHeading(DocumentApp.ParagraphHeading.HEADING2)
      .setFontFamily(CONFIG.FONT_FAMILY)
      .setBold(true)
      .setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  body.appendParagraph("Project: " + (unitId || ""))
      .setFontFamily(CONFIG.FONT_FAMILY)
      .setFontSize(10);
  body.appendParagraph("Scope: HVAC Works")
      .setFontFamily(CONFIG.FONT_FAMILY)
      .setFontSize(10);
  body.appendParagraph("");

  const tableRows = [["No.", "Item", "Unit", "Qty", "Rate", "Total (EGP)"]];
  scopeItems.forEach(item => {
    // Rate and Total are deliberately forced blank here. The detailed scope
    // must never expose or duplicate the internal commercial calculation.
    tableRows.push([
      String(item["No."] || ""),
      String(item["Item"] || ""),
      String(item["Unit"] || ""),
      item["QTY"] === "" || item["QTY"] == null ? "" : String(item["QTY"]),
      "",
      ""
    ]);
  });

  const table = body.appendTable(tableRows);
  table.setAttributes({
    [DocumentApp.Attribute.FONT_FAMILY]: CONFIG.FONT_FAMILY,
    [DocumentApp.Attribute.FONT_SIZE]: 9
  });

  for (let rowIndex = 0; rowIndex < table.getNumRows(); rowIndex++) {
    const row = table.getRow(rowIndex);
    const scopeItem = rowIndex > 0 ? scopeItems[rowIndex - 1] : null;
    const rowType = scopeItem ? String(scopeItem["Row Type"] || "item") : "header";

    for (let cellIndex = 0; cellIndex < row.getNumCells(); cellIndex++) {
      const cell = row.getCell(cellIndex);
      cell.setVerticalAlignment(DocumentApp.VerticalAlignment.CENTER);
      cell.setPaddingTop(2);
      cell.setPaddingBottom(2);
      cell.setPaddingLeft(2);
      cell.setPaddingRight(2);

      if (rowType === "section") {
        cell.setBackgroundColor("#EDEDED");
      }

      const alignment = cellIndex === 1 && rowType === "item"
        ? DocumentApp.HorizontalAlignment.LEFT
        : DocumentApp.HorizontalAlignment.CENTER;
      for (let childIndex = 0; childIndex < cell.getNumChildren(); childIndex++) {
        const child = cell.getChild(childIndex);
        if (child.getType() === DocumentApp.ElementType.PARAGRAPH) {
          child.asParagraph().setAlignment(alignment);
        }
      }
    }

    if (rowType === "header" || rowType === "section" || rowType === "total") {
      row.setAttributes({ [DocumentApp.Attribute.BOLD]: true });
    }
  }

  table.setColumnWidth(0, 36.0);
  table.setColumnWidth(1, 300.0);
  table.setColumnWidth(2, 43.2);
  table.setColumnWidth(3, 43.2);
  table.setColumnWidth(4, 57.6);
  table.setColumnWidth(5, 72.0);
}

function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents);
    const action = payload.action || "standard";
    
    // Check request type for dynamic folder/template assignment
    const reqTypeStr = payload.requestType ? payload.requestType.toString().toUpperCase().trim() : "";
    const isLandExtension = reqTypeStr.includes("LAND EXTENSION");
    
    // Streamlit identifies Furniture explicitly so custom Option O quotations
    // use the correct template and folders even when the name does not start
    // with "1 Bedroom", "2 Bedrooms", etc.
    const isFurniture = String(payload.requestCategory || "").toUpperCase() === "FURNITURE"
      || /^\d+\s+BEDROOM/.test(reqTypeStr);
    const isAc = String(payload.requestCategory || "").toUpperCase() === "A.C"
      || reqTypeStr === "A.C";

    const destFolderId = isFurniture ? CONFIG.FURNITURE_DOC_FOLDER_ID : CONFIG.DESTINATION_FOLDER_ID;
    const pdfFolderId = isFurniture ? CONFIG.FURNITURE_PDF_FOLDER_ID : CONFIG.PDF_DESTINATION_FOLDER_ID;

    const destFolder = DriveApp.getFolderById(destFolderId);
    const pdfFolder = DriveApp.getFolderById(pdfFolderId);

    // --- PART A: SAVING MERGED PDF FROM PYTHON ---
    if (action === "uploadPdf") {
      const blob = Utilities.newBlob(Utilities.base64Decode(payload.base64Pdf), 'application/pdf', payload.docName);
      
      // Save directly to the correctly determined PDF folder
      const pdfFile = pdfFolder.createFile(blob); 
      
      try {
        pdfFile.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
      } catch (sharingError) {
        console.warn("Sharing permission blocked by Workspace, but PDF was created successfully.");
      }
      
      logGeneratedQuote({
        serial: payload.serialNumber,
        unit: payload.unitId,
        client: payload.clientName,
        requestType: payload.requestType,
        total: payload.grandTotal,
        zone: payload.zone
      });
      
      return ContentService.createTextOutput(JSON.stringify({
        status: "success",
        pdfUrl: pdfFile.getUrl()
      })).setMimeType(ContentService.MimeType.JSON);
    }

    // --- PART B: STANDARD DOC GENERATION SETUP ---
    if (!payload.items || payload.items.length === 0) {
      return ContentService.createTextOutput(JSON.stringify({status: "error", message: "No items provided."})).setMimeType(ContentService.MimeType.JSON);
    }
    
    const formattedItems = payload.items.map(item => ({
      description: item.description,
      unit: item.unit,
      qty: item.qty,
      rate: item.rate,
      baseKey: item.baseKey || "",
      total: (Number(item.qty) || 0) * (Number(item.rate) || 0)
    }));

    // --- SPECIAL CONDITION: LAND EXTENSION ---
    if (isLandExtension) {
      let area = 0;

      // Streamlit sends the selected rate explicitly. Keep the first item's
      // rate as a compatibility fallback for older Streamlit deployments.
      const rawLandExtensionRate = payload.landExtensionRate != null
        ? payload.landExtensionRate
        : (formattedItems.length > 0 ? formattedItems[0].rate : null);
      const selectedLandExtensionRate = Number(
        String(rawLandExtensionRate == null ? "" : rawLandExtensionRate).replace(/,/g, "")
      );

      if (!CONFIG.LAND_EXTENSION_ALLOWED_RATES.includes(selectedLandExtensionRate)) {
        throw new Error(
          "Invalid Land Extension rate. Please select EGP 55,000/m2 or EGP 65,000/m2 in Streamlit."
        );
      }
      
      // Attempt to locate the area input 
      if (formattedItems.length > 0) {
        let parsedDesc = parseFloat(formattedItems[0].description);
        if (!isNaN(parsedDesc) && parsedDesc > 0) {
          area = parsedDesc;
        } else {
          area = parseFloat(formattedItems[0].qty) || 0;
        }
      }

      // Fallback: If area is still 0, check if payload passed a specific "area" property
      if (area === 0 && payload.area && !isNaN(parseFloat(payload.area))) {
        area = parseFloat(payload.area);
      }

      // Modify ONLY the first row, keeping any additional rows intact
      if (formattedItems.length > 0) {
        formattedItems[0].description = "Required Fees for Adding land extension area of for a/m unit as per attached Drawings.";
        formattedItems[0].unit = "M2";
        formattedItems[0].qty = area;
        formattedItems[0].rate = selectedLandExtensionRate;
        formattedItems[0].total = area * selectedLandExtensionRate;
      } else {
        formattedItems.push({
          description: "Required Fees for Adding land extension area of for a/m unit as per attached Drawings.",
          unit: "M2",
          qty: area,
          rate: selectedLandExtensionRate,
          total: area * selectedLandExtensionRate
        });
      }
    }

    if (formattedItems.length === 0) {
      return ContentService.createTextOutput(JSON.stringify({status: "error", message: "No valid items to process."})).setMimeType(ContentService.MimeType.JSON);
    }

    const serialNumber = getUniqueSerialNumber();
    const docName = `${payload.unitId} - ${serialNumber} - ${payload.requestType}`;
    
    let subTotal = 0;
    formattedItems.forEach(item => { subTotal += item.total; });
    
    const vatRate = isLandExtension ? 0.0 : 0.14;
    const vatAmount = subTotal * vatRate;
    const grandTotal = subTotal + vatAmount;
    
    const moneyWords = isLandExtension 
      ? `Only ${convertNumberToWords(grandTotal)} Egyptian Pound & Zero Piaster`
      : `Only ${convertNumberToWords(grandTotal)} Egyptian Pound & ${Math.round((grandTotal - Math.floor(grandTotal)) * 100)}/100 Piaster`;
    
    // Dynamic Template Selection
    let templateId = CONFIG.TEMPLATE_ID;
    if (isLandExtension) templateId = CONFIG.LAND_EXTENSION_TEMPLATE_ID;
    if (isFurniture) templateId = CONFIG.FURNITURE_TEMPLATE_ID;

    const templateFile = DriveApp.getFileById(templateId);
    
    const docCopy = templateFile.makeCopy(docName, destFolder);
    const docId = docCopy.getId();
    const doc = DocumentApp.openById(docId);
    const body = doc.getBody();

    const formattedDate = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "dd-MMM-yyyy");
    body.replaceText("{{unit}}", payload.unitId || "");
    body.replaceText("{{client}}", payload.clientName || "");
    body.replaceText("{{zone}}", payload.zone || "");
    body.replaceText("{{request}}", payload.requestType || "");
    body.replaceText("{{date}}", formattedDate);
    body.replaceText("{{number}}", serialNumber);
    body.replaceText("{{subtotal}}", Number(subTotal).toLocaleString('en-US', {minimumFractionDigits: 2}));
    body.replaceText("{{vat}}", Number(vatAmount).toLocaleString('en-US', {minimumFractionDigits: 2}));
    body.replaceText("{{total}}", Number(grandTotal).toLocaleString('en-US', {minimumFractionDigits: 2}));
    body.replaceText("{{word}}", moneyWords);

    // Streamlit-generated terms are authoritative for this quotation.
    // The APP sheet remains the fallback for older callers and manual runs.
    const generatedTerms = String(payload.generatedTermsAndConditions || "").trim();
    const termsText = generatedTerms || getTermsAndConditions(payload.requestType);
    const termsRange = body.findText("{{terms}}");
    if (termsRange) {
      const element = termsRange.getElement();
      const parentPara = element.getParent();
      const index = body.getChildIndex(parentPara);
      body.removeChild(parentPara);
      
      if (termsText) {
        const termLines = termsText.toString().split('\n');
        termLines.reverse().forEach(line => { 
          if(line.trim() !== "") {
            body.insertListItem(index, line.trim())
                .setGlyphType(DocumentApp.GlyphType.BULLET)
                .setFontFamily(CONFIG.FONT_FAMILY)
                .setFontSize(9)
                .setBold(false);
          }
        });
      }
    }

    const searchResult = body.findText("{{table}}");
    if (searchResult) {
      const element = searchResult.getElement();
      const parent = element.getParent();
      const index = body.getChildIndex(parent);
      body.removeChild(parent); 
      
      const tableHeader = [["No.", "Description", "Unit", "QTY", "Rate", "Total Amount"]];
      const tableRows = formattedItems.map((item, idx) => [
        String(idx + 1),
        String(item.description),
        String(item.unit),
        String(item.qty),
        Number(item.rate).toLocaleString('en-US', {minimumFractionDigits: 2}),
        Number(item.total).toLocaleString('en-US', {minimumFractionDigits: 2})
      ]);
      
      const table = body.insertTable(index, tableHeader.concat(tableRows));
      
      table.setAttributes({ 
        [DocumentApp.Attribute.FONT_FAMILY]: CONFIG.FONT_FAMILY,
        [DocumentApp.Attribute.FONT_SIZE]: 10,
        [DocumentApp.Attribute.INDENT_START]: -36 
      });

      for (let r = 0; r < table.getNumRows(); r++) {
        const row = table.getRow(r);
        for (let c = 0; c < row.getNumCells(); c++) {
          const cell = row.getCell(c);
          cell.setVerticalAlignment(DocumentApp.VerticalAlignment.CENTER);
          cell.setPaddingTop(0); cell.setPaddingBottom(0); cell.setPaddingLeft(0); cell.setPaddingRight(0);

          let alignment = DocumentApp.HorizontalAlignment.CENTER;
          if (r > 0 && c === 1) alignment = DocumentApp.HorizontalAlignment.LEFT;

          const numChildren = cell.getNumChildren();
          for (let p = 0; p < numChildren; p++) {
            const child = cell.getChild(p);
            if (child.getType() === DocumentApp.ElementType.PARAGRAPH) {
              child.asParagraph().setAlignment(alignment);
            }
          }
        }
      }

      table.getRow(0).setAttributes({ [DocumentApp.Attribute.BOLD]: true });
      
      table.setColumnWidth(0, 28.8);    // No. (0.4")
      table.setColumnWidth(1, 288.0);   // Description (4.0")
      table.setColumnWidth(2, 36.0);    // Unit (0.5")
      table.setColumnWidth(3, 23.76);   // Qty (0.33")
      table.setColumnWidth(4, 72.576);  // Rate (1.008")
      table.setColumnWidth(5, 81.36);   // Total (1.13")
    }

    if (isAc) {
      appendAcDetailedScope(
        body,
        payload.detailedScopeItems || [],
        payload.unitId || ""
      );
    }

    doc.saveAndClose();
    const docUrl = doc.getUrl();

    // --- PART C: ACTION HANDLING (PYTHON MERGING OR STANDARD PDF EXTRACT) ---
    if (action === "generateDocOnly") {
      // ADVANCED PDF MERGE PREPARATION FOR FURNITURE
      const ROOM_PDF_FOLDER_ID = "1CRILRUeUpqwd4UplFXIVqVlFD4tcc631";
      const roomFolder = DriveApp.getFolderById(ROOM_PDF_FOLDER_ID);
      const roomBase64s = [];
      const missingRoomPdfs = [];
      
      payload.items.forEach(item => {
        const descUpper = String(item.description).toUpperCase();
        const exactBaseKey = String(item.baseKey || "").toUpperCase().trim();
        let searchName = "";
        
        // Prefer the exact per-room P1/P2/P3 design selected in Streamlit.
        // Kitchen, Closets and AC keys intentionally have no room-design PDF.
        if (/^(RECEPTION|DINING ROOM|TERRACE|OUTDOORS|MASTER BEDROOM|KIDS BEDROOM|LIVING ROOM) - P[123]$/.test(exactBaseKey)) {
          searchName = exactBaseKey;
        } else if (exactBaseKey === "NANNY'S ROOM") {
          searchName = "NANNY";
        } else if (!exactBaseKey) {
          // Backward-compatible fallback for older Streamlit payloads.
          if (descUpper.includes("NANNY")) {
            searchName = "NANNY";
          } else {
            if (descUpper.includes("RECEPTION")) searchName = "RECEPTION";
            else if (descUpper.includes("DINING")) searchName = "DINING";
            else if (descUpper.includes("TERRACE")) searchName = "TERRACE";
            else if (descUpper.includes("OUTDOORS")) searchName = "OUTDOORS";
            else if (descUpper.includes("MASTER BEDROOM")) searchName = "MASTER BEDROOM";
            else if (descUpper.includes("KIDS BEDROOM")) searchName = "KIDS BEDROOM";
            else if (descUpper.includes("LIVING")) searchName = "LIVING";
            
            if (searchName && payload.packageCode) {
              searchName = `${searchName} - ${payload.packageCode}`;
            }
          }
        }
        
        if (searchName) {
          const files = roomFolder.searchFiles(`title contains '${searchName}'`);
          if (files.hasNext()) {
            const file = files.next();
            roomBase64s.push(Utilities.base64Encode(file.getBlob().getBytes()));
          } else {
            missingRoomPdfs.push(searchName);
          }
        }
      });
      
      try { docCopy.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.EDIT); } catch(e){}
      const docBase64 = Utilities.base64Encode(docCopy.getAs('application/pdf').getBytes());
      
      return ContentService.createTextOutput(JSON.stringify({
        status: "success",
        docUrl: docUrl,
        docName: `${docName}.pdf`,
        docBase64: docBase64,
        roomBase64s: roomBase64s,
        missingRoomPdfs: missingRoomPdfs,
        serialNumber: serialNumber,
        grandTotal: grandTotal
      })).setMimeType(ContentService.MimeType.JSON);

    } else {
      // 🚀 NEW ENGINE: Compile a static PDF clone of this doc directly on Drive
      const docFile = DriveApp.getFileById(docId);
      const pdfBlob = docFile.getAs(MimeType.PDF);
      
      // Create the PDF in the dedicated PDF Folder
      const pdfFile = pdfFolder.createFile(pdfBlob);
      pdfFile.setName(docName + ".pdf");
      
      // Set direct public view permissions safely
      try {
        pdfFile.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
      } catch (sharingError) {
        console.warn("Sharing permission blocked by Workspace, but PDF was created successfully.");
      }
      
      const pdfUrl = pdfFile.getUrl();

      logGeneratedQuote({
        serial: serialNumber,
        unit: payload.unitId,
        client: payload.clientName,
        requestType: payload.requestType,
        total: grandTotal,
        zone: payload.zone
      });

      return ContentService.createTextOutput(JSON.stringify({
        status: "success", 
        docUrl: docUrl,
        pdfUrl: pdfUrl
      })).setMimeType(ContentService.MimeType.JSON);
    }

  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "error", 
      message: error.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}
