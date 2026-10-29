# Apps Script bridge deployment

The deployed Apps Script remains the private Google Workspace rendering and
storage bridge. Business rules and final Terms & Conditions are owned by the
Streamlit application.

## Apply the Option B patch

1. Open the Apps Script project used by the quotation webhook.
2. Add the function from `webhook_terms_patch.gs` anywhere at top level.
3. Inside `doPost(e)`, find:

   ```javascript
   const termsText = getTermsAndConditions(payload.requestType);
   ```

4. Replace it with:

   ```javascript
   const termsText = resolveWebhookTerms_(payload);
   ```

5. Save the project.
6. Open **Deploy -> Manage deployments**.
7. Edit the existing Web App deployment, select **New version**, and deploy.
8. Keep the existing Web App URL. No GitHub webhook URL change is required.

## Backward compatibility

New Streamlit quotations send `generatedTermsAndConditions`. Existing Google
Form and older webhook calls continue using `getTermsAndConditions(requestType)`
when that field is absent.

## O-PLUS quotation design (new PDF layout)

Streamlit now renders the client PDF itself in the O-PLUS design (the layout of
quotation 1778) and uses two existing webhook actions:

1. `generateDocOnly` – creates the Google Doc and serial number. Streamlit sends
   `shareDocForEdit: false`, `includeDocPdf: false`, `includeRoomPdfs: false`,
   and the script now also returns `formattedDate`, `vatRate`, `subTotal` and
   the final `items`.
2. `uploadPdf` – saves the new-design PDF to the Drive PDF folder and logs the
   quotation in the log sheet.

After pulling this change, paste the updated `Code.gs` into the Apps Script
project and deploy a **New version** of the existing Web App (same URL).
Until then the old script still works, but it shares the Google Doc with
"anyone with the link can edit".
