/**
 * OPTION B BRIDGE PATCH
 *
 * Apply this replacement inside doPost(e), where the webhook currently loads:
 *
 *   const termsText = getTermsAndConditions(payload.requestType);
 *
 * This keeps older form and webhook calls backward compatible while allowing
 * Streamlit to provide the final quotation-specific Terms & Conditions.
 */

function resolveWebhookTerms_(payload) {
  const generatedTerms = payload && payload.generatedTermsAndConditions;
  if (generatedTerms && String(generatedTerms).trim()) {
    return String(generatedTerms);
  }
  return getTermsAndConditions(payload.requestType);
}

// In doPost(e), replace the existing terms lookup with:
// const termsText = resolveWebhookTerms_(payload);
