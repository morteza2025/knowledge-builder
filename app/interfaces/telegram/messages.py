from __future__ import annotations

from app.interfaces.telegram.job_models import JobState, TelegramJob


START_TEXT = (
    "سلام! فایل PDF آموزشی را مستقیم یا فورواردشده بفرستید. "
    "فایل با استخراج متن و OCR پشتیبان پردازش می‌شود."
)

HELP_TEXT = """فقط فایل PDF پذیرفته می‌شود.
فایل مستقیم و فورواردشده هر دو پشتیبانی می‌شوند.
برای فایل‌های بزرگ، ربات از Telegram Local Bot API Server استفاده می‌کند.
وضعیت‌ها شامل صف، دریافت، استخراج، OCR، ساخت خروجی و پایان است.
خروجی‌های JSON، Markdown و خروجی‌های ساختاری موجود ارسال می‌شوند.
/status وضعیت آخرین کار شما را نشان می‌دهد.
/cancel کار در صف را فوراً لغو می‌کند؛ کار در حال اجرا در نزدیک‌ترین مرز امن متوقف می‌شود.
دسترسی ربات محدود به کاربران مجاز است."""

UNAUTHORIZED_TEXT = "⛔️ شما اجازه استفاده از این ربات را ندارید."
NON_PDF_TEXT = "❌ فقط فایل PDF معتبر پذیرفته می‌شود."
QUEUE_FULL_TEXT = "⏳ صف پردازش پر است؛ لطفاً کمی بعد دوباره تلاش کنید."
NO_JOB_TEXT = "هنوز کاری برای شما ثبت نشده است."
NO_CANCELLABLE_JOB_TEXT = "کار قابل لغوی برای شما پیدا نشد."
DELIVERY_FAILED_TEXT = (
    "✅ پردازش فایل کامل شد، اما ارسال یک یا چند خروجی در تلگرام ناموفق بود. "
    "فایل‌های ساخته‌شده حفظ شده‌اند."
)


_STATE_LABELS = {
    JobState.received: "✅ فایل دریافت شد",
    JobState.validating: "🔎 در حال اعتبارسنجی فایل",
    JobState.queued: "⏳ در صف پردازش",
    JobState.downloading: "📥 در حال آماده‌سازی فایل",
    JobState.ready: "✅ فایل آماده پردازش است",
    JobState.processing: "⚙️ در حال پردازش",
    JobState.extracting: "📖 در حال استخراج متن",
    JobState.ocr: "🔎 در حال اجرای OCR",
    JobState.exporting: "📦 در حال ساخت خروجی‌ها",
    JobState.completed: "✅ پردازش کامل شد",
    JobState.failed: "❌ پردازش ناموفق بود",
    JobState.cancel_requested: "🛑 درخواست لغو ثبت شد",
    JobState.cancelled: "🛑 پردازش لغو شد",
}


def state_label(state: JobState) -> str:
    return _STATE_LABELS[state]


def format_status(job: TelegramJob, queue_position: int | None = None) -> str:
    lines = [
        state_label(job.state),
        f"شناسه: {job.id}",
        f"فایل: {job.filename}",
    ]
    if queue_position is not None:
        lines.append(f"جایگاه صف: {queue_position}")
    if job.total_pages is not None:
        lines.append(f"تعداد صفحات: {job.total_pages}")
    if job.processed_pages is not None:
        lines.append(f"صفحات پردازش‌شده: {job.processed_pages}")
    if job.ocr_page_count is not None:
        lines.append(f"صفحات OCR شده: {job.ocr_page_count}")
    lines.append(f"زمان سپری‌شده: {job.elapsed_seconds} ثانیه")
    if job.state == JobState.completed:
        lines.append(f"تعداد خروجی‌ها: {len(job.output_paths)}")
    if job.state == JobState.failed and job.error_summary:
        lines.append(f"علت: {job.error_summary}")
    return "\n".join(lines)


def completion_summary(job: TelegramJob) -> str:
    warning_text = f"\nهشدارها: {len(job.warnings)}" if job.warnings else ""
    return (
        "✅ پردازش با موفقیت تمام شد.\n"
        f"فایل: {job.filename}\n"
        f"صفحات: {job.total_pages or 0}\n"
        f"صفحات OCR شده: {job.ocr_page_count or 0}\n"
        f"خروجی‌ها: {len(job.output_paths)}"
        f"{warning_text}"
    )
