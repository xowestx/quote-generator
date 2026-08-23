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
