#pragma once

#include <QDebug>
#include <QLoggingCategory>

Q_DECLARE_LOGGING_CATEGORY(Librepods)

#define LOG_INFO(msg) qCInfo(Librepods) << "\033[32m" << msg << "\033[0m"
#define LOG_WARN(msg) qCWarning(Librepods) << "\033[33m" << msg << "\033[0m"
#define LOG_ERROR(msg) qCCritical(Librepods) << "\033[31m" << msg << "\033[0m"
#define LOG_DEBUG(msg) qCDebug(Librepods) << "\033[34m" << msg << "\033[0m"
