# Garden Care Website — MVP Specification

## 1. Project Overview

A cosy, friendly, data-led gardening website that helps users identify plants, build a personal plant collection, and receive professional plant-care guidance and gentle seasonal reminders.

The MVP is designed for a course project with fewer than 100 users.

### Goals
- Allow users to register and manage their own plant collection.
- Identify plants through search and, if feasible, photo matching.
- Retrieve professional plant information from external APIs.
- Store reusable plant data in a database, subject to API licensing.
- Provide location-aware seasonal gardening suggestions.
- Offer optional weekly gardening emails.
- Establish a foundation for future community features.

## 2. Target Users

- Beginners who want straightforward plant-care guidance.
- Home gardeners who want to keep track of their plants.
- Enthusiasts focused on flowers, vegetables, houseplants or other plant types.

Community features are a possible future addition, not a core MVP requirement.

## 3. MVP Features

### Included
- User registration, login and logout.
- Country or regional preferences.
- Plant search by common or scientific name.
- Optional photo-based plant identification.
- User confirmation of plant identification.
- Personal plant collection.
- Plant information and care guidance.
- Dashboard with garden overview.
- Seasonal gardening suggestions.
- Optional weekly email summaries.
- Account and email preferences.
- Responsive, accessible interface.

### Excluded Initially
- Community feeds, comments and messaging.
- Shared gardens.
- Detailed garden beds, planters and greenhouse layouts.
- Custom-trained machine-learning models.
- Advanced weather forecasting.
- Sensor integrations.
- Native mobile applications.
- Paid subscriptions and complex gamification.

## 4. User Journey

1. Visit the landing page.
2. Register or log in.
3. Select a country or region.
4. Open the garden dashboard.
5. Search for a plant or upload a photo.
6. Review and confirm the identification.
7. Add the plant to My Garden.
8. View its care information and seasonal suggestions.
9. Receive a weekly email if opted in.
10. Manage plants and preferences at any time.

## 5. Functional Requirements

### 5.1 Authentication
Users can register, log in, log out and reset their password.

Authentication should use a reputable provider or established framework. Passwords must never be stored in plaintext.

Users must only access their own private garden records.

### 5.2 Location
Users select their country, such as the UK or US.

The application uses this preference to inform seasonal guidance. Users can change their location without providing precise GPS coordinates.

Country-level guidance is sufficient for the initial MVP, although regional differences must be acknowledged.

### 5.3 Plant Search
Users can search using common names or scientific names.

Results should display available names, images and identifying information. Users explicitly select a result before saving it.

### 5.4 Photo Identification
Users may upload a photograph to an existing plant-identification API.

The service returns possible matches. Users must confirm the correct plant before adding it.

Requirements:
- No custom model training.
- Validate uploaded image types and sizes.
- Check API pricing, coverage and licensing.
- Provide manual search as a fallback.
- Avoid unnecessary image retention.

Photo identification can be deferred if it exceeds the course budget or timeline.

### 5.5 Personal Plant Collection
Users can:
- Add plants.
- View their collection.
- Open plant detail pages.
- Remove plants.
- Add optional personal notes.
- See when plants were added.

Detailed garden layouts and planter management are outside the initial scope.

### 5.6 Plant Information
Display available professional information:
- Common and scientific names.
- Description.
- Image, where licensed.
- Care guidance.
- Seasonal or planting information, where available.
- Source attribution, where required.

Care categories may include watering, pruning, deadheading, sowing, planting, feeding, flowering and harvesting.

Do not invent care advice when reliable information is unavailable.

### 5.7 Dashboard
The logged-in dashboard contains:

**Garden overview**
- Friendly greeting.
- Plant collection.
- Plant count.
- Clear Add a Plant action.
- Helpful empty state.

**Care suggestions**
- Relevant upcoming plant-care activities.
- Friendly recommendations rather than mandatory tasks.
- Options to dismiss or mark suggestions complete.

**Seasonal highlights**
- A small selection of appropriate activities based on plant information, season and user location.

### 5.8 Seasonal Guidance
Recommendations should use:
- Plant-care requirements.
- Current date and season.
- User's selected country or region.
- Available planting, flowering and pruning data.

Clearly distinguish professional plant information from location-dependent seasonal recommendations.

Recommendations are guidance, not guarantees. Account for hemispheres and regional climate variation where possible.

### 5.9 Weekly Emails
Users may opt in to receive a weekly gardening email.

Emails include:
- Friendly introduction.
- Relevant plants from the user's collection.
- A few seasonal suggestions.
- Links back to the dashboard.

Users can turn emails off and unsubscribe. Avoid duplicate messages and repetitive suggestions.

Use a managed email provider and scheduled server-side process where practical.

## 6. Design and User Experience

### Visual Direction
A mix of modern botanical design and cosy, playful game-inspired elements, taking inspiration from the approachable feel of Stardew Valley and Cooking Mama without copying their artwork or interface.

### Visual Characteristics
- Sage green and muted botanical greens.
- Warm cream backgrounds.
- Earthy accent colours.
- Rounded cards and buttons.
- Friendly plant illustrations.
- Clear typography.
- Simple icons.
- Subtle decorative details.

### Navigation
- Dashboard.
- My Garden.
- Add a Plant.
- Settings.

Navigation should be consistent across desktop and mobile.

### Accessibility
- Readable text and sufficient colour contrast.
- Labels for form controls.
- Keyboard-friendly navigation.
- Meaningful alternative text.
- Visible loading, success and error states.
- Reduced-motion support if animations are added.

## 7. Technical Architecture

Use a lightweight, managed architecture suitable for a small course project.

Components:
1. Frontend application.
2. Managed authentication.
3. Hosted relational database.
4. Professional plant data API.
5. Optional plant identification API.
6. Managed email service.
7. Scheduled server-side process.

Select specific technologies based on course requirements, existing skills, API compatibility and free-tier availability.

### Data Flow
1. User searches for a plant or uploads a photo.
2. Backend calls the relevant API.
3. Application validates the response.
4. Permitted reusable plant information is stored or cached.
5. User confirms the plant.
6. Garden entry is saved.
7. Dashboard retrieves the user's collection.
8. Relevant care suggestions are generated.
9. A scheduled process prepares weekly emails for opted-in users.

API keys must remain on the server.

### Caching
Store reusable plant records only as permitted by the API licence. Use stable provider identifiers and avoid duplicating plant records for every user.

## 8. Proposed Database Structure

### Users
- `id`
- `email`
- `country_code`
- `region`
- `weekly_email_enabled`
- `created_at`
- `updated_at`

Authentication credentials should be managed by the authentication service.

### Plants
- `id`
- `provider`
- `provider_plant_id`
- `common_name`
- `scientific_name`
- `description`
- `image_url`
- `care_data`
- `source_url`
- `last_synced_at`
- `created_at`
- `updated_at`

Add a unique constraint for provider and provider plant ID.

### Garden Entries
- `id`
- `user_id`
- `plant_id`
- `date_added`
- `personal_notes`
- `created_at`
- `updated_at`

### Care Suggestions
- `id`
- `user_id`
- `garden_entry_id`
- `task_type`
- `suggestion_text`
- `suggested_date`
- `source`
- `status`
- `created_at`
- `updated_at`

Possible statuses: `suggested`, `dismissed`, `completed`.

Ignoring a suggestion should not automatically create an overdue task.

### Email Delivery Records
- `id`
- `user_id`
- `email_type`
- `scheduled_for`
- `sent_at`
- `provider_message_id`
- `delivery_status`

Use records to support basic delivery tracking and duplicate prevention.

### Relationships
- One user has many garden entries.
- One plant can appear in many garden entries.
- One garden entry can have many care suggestions.
- One user can have many email delivery records.

Protect all user-owned records with appropriate access policies.

## 9. Plant API Evaluation

Before choosing a provider, evaluate:
- Coverage of common garden plants.
- Scientific names and synonyms.
- Quality of professional care information.
- Seasonal and planting data.
- Image licensing.
- Search capabilities.
- Rate limits.
- Free-tier restrictions.
- Educational and commercial use permissions.
- Caching and redistribution rules.
- API reliability and documentation.

A taxonomy API may not provide complete horticultural care guidance. A separate source may be needed for identification and care advice.

Track data provenance and display attribution when required.

## 10. Cost Management

Keep costs low by:
- Using managed hosting and database services.
- Using free tiers where appropriate.
- Avoiding custom model training.
- Analysing photos only when requested.
- Caching permitted plant records.
- Compressing uploaded images.
- Sending one optional weekly email.
- Avoiding unnecessary background infrastructure.

Potential costs include hosting, database usage, plant API calls, photo identification, image storage and email delivery.

Check current pricing, usage limits and licensing before selecting providers.

## 11. Privacy and Security

- Require authentication for garden management.
- Restrict users to their own private records.
- Apply database access policies and server-side authorisation.
- Keep API credentials out of frontend code.
- Validate uploaded files.
- Collect only necessary personal information.
- Allow users to manage email preferences.
- Provide an account deletion process.
- Follow applicable privacy and email requirements.
- Do not use uploaded photos for model training without appropriate permissions and disclosure.

## 12. Error Handling

**Plant API unavailable:** Explain the problem and allow retrying.

**Photo identification fails:** Offer manual search.

**Plant information is incomplete:** Display available data and identify missing information.

**Email delivery fails:** Record failures where possible and avoid duplicate sends.

**Garden is empty:** Show a welcoming message and an Add a Plant action.

**No seasonal suggestions are available:** Avoid fabricating advice; display only supported general guidance.

## 13. Implementation Plan

### Phase 1 — Foundation
- Set up repository and project.
- Choose technology stack.
- Implement authentication.
- Create database schema.
- Establish design system and responsive navigation.

### Phase 2 — Plant Collection
- Implement plant search.
- Integrate plant data API.
- Store permitted plant records.
- Support adding, viewing and removing plants.
- Build plant detail pages.

### Phase 3 — Dashboard
- Build garden overview.
- Display care information.
- Implement seasonal suggestions.
- Handle missing data and empty states.

### Phase 4 — Photo Identification
- Select and integrate identification API.
- Implement image upload and validation.
- Display candidate matches.
- Require user confirmation.
- Provide manual-search fallback.

### Phase 5 — Weekly Emails
- Implement email preferences.
- Create email template.
- Generate personalised summaries.
- Schedule delivery.
- Implement unsubscribe and delivery tracking.

### Phase 6 — Testing
- Test authentication and permissions.
- Test plant search and saving.
- Verify API failure handling.
- Test email preferences and delivery.
- Review accessibility and mobile layouts.
- Check data quality and source attribution.
- Test with a small group of users.

## 14. Acceptance Criteria

### Authentication
- Users can register, log in and log out.
- Users can access their own gardens.
- Users cannot access other users' private records.

### Plant Collection
- Users can search and select plants.
- Plants appear in the saved collection.
- Users can view details and remove plants.
- Saved plants persist across sessions.

### Plant Information
- Available plant information is displayed.
- Data sources are tracked where practical.
- Missing information is not fabricated.
- API errors are handled gracefully.

### Photo Identification
- Accepted images can be uploaded.
- Candidate matches are shown when identification succeeds.
- Users confirm matches before saving.
- Manual search remains available.

Photo identification may be deferred if excluded from the first demonstrable build.

### Dashboard
- Displays the user's plant collection.
- Shows relevant seasonal highlights.
- Uses plant data and location preferences.
- Provides a useful empty state.

### Email
- Users can enable or disable weekly emails.
- Emails contain relevant suggestions.
- Unsubscribe is available.
- Scheduling avoids duplicate sends.

### User Experience
- Works on mobile and desktop.
- Navigation is clear.
- Text is readable and accessible.
- Reminders use friendly, non-pressuring language.

## 15. Future Development

Possible enhancements:
- Community profiles and garden sharing.
- Posts, comments and gardening advice.
- Collaborative gardens.
- Beds, borders, pots and greenhouse layouts.
- Vegetable crop planning.
- More precise regional climate data.
- Weather-aware recommendations.
- User-defined reminders.
- Growth journals and photographs.
- Optional achievements and game-inspired progression.

Prioritise these only after validating the initial plant-care experience.

## 16. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Plant API lacks care data | Evaluate quality before selection; use an additional reputable source if needed. |
| Photo identification is expensive | Use an existing API, limit requests and provide manual search. |
| Seasonal advice is too generic | Start with country-level guidance and document limitations. |
| Licensing restricts caching | Review terms and store only permitted information. |
| Scope becomes too large | Prioritise plant search, collection and dashboard. |
| Email scheduling adds complexity | Use a managed email service and simple scheduled process. |
| Recommendations are inaccurate | Track sources, avoid unsupported advice and communicate uncertainty. |

## 17. Definition of Success

The MVP is successful when a user can:

1. Create an account.
2. Identify a plant through search and, optionally, photo matching.
3. Add the plant to a personal collection.
4. View reliable plant information.
5. Receive relevant seasonal guidance.
6. Opt in to a friendly weekly email.
7. Manage their collection and preferences.

The result should be a small, polished and usable plant-care application rather than a large collection of unfinished features.

**Core product promise:** Help people enjoy caring for their plants by making professional gardening knowledge approachable, personal and timely.