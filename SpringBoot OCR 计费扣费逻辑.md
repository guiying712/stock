没问题，这套 **Spring Boot + Redis Lua + PostgreSQL + MyBatis** 的完整高并发计费方案代码如下。

我将代码拆分为了清晰的文件结构，你可以按照包路径直接复制并在你的项目中使用。

### 1. 准备工作

#### 1.1 `pom.xml` 依赖

确保你包含以下核心依赖（版本号根据你的 SpringBoot 版本调整）：

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.mybatis.spring.boot</groupId>
        <artifactId>mybatis-spring-boot-starter</artifactId>
        <version>3.0.3</version>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
    </dependency>
    <dependency>
        <groupId>org.projectlombok</groupId>
        <artifactId>lombok</artifactId>
    </dependency>
</dependencies>

```

#### 1.2 数据库初始化 SQL (PostgreSQL)

```sql
CREATE TABLE IF NOT EXISTS user_wallet (
    id SERIAL PRIMARY KEY,
    app_id VARCHAR(64) NOT NULL,
    total_purchased BIGINT NOT NULL DEFAULT 0,
    used_count BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_app_id UNIQUE (app_id)
);

CREATE INDEX idx_user_wallet_app_id ON user_wallet(app_id);

```

#### 1.3 Lua 脚本文件

在 `src/main/resources/scripts` 目录下创建文件 `deduct_hash.lua`:

```lua
-- keys[1]: wallet:{app_id}
-- argv[1]: cost
local key = KEYS[1]
local cost = tonumber(ARGV[1])

-- 读取 Hash 中的 total 和 used
local values = redis.call('HMGET', key, 'total', 'used')
local total = tonumber(values[1])
local used = tonumber(values[2])

-- 如果缓存不存在，返回 -1
if total == nil or used == nil then
    return -1
end

-- 判断余额是否充足
if (total - used) >= cost then
    -- 原子增加 used 字段
    redis.call('HINCRBY', key, 'used', cost)
    return 1 -- 成功
else
    return 0 -- 余额不足
end

```

---

### 2. Java 后端代码

#### 2.1 实体类 `UserWallet.java`

```java
package com.example.ocr.entity;

import lombok.Data;
import java.time.LocalDateTime;

@Data
public class UserWallet {
    private Long id;
    private String appId;
    private Long totalPurchased;
    private Long usedCount;
    private LocalDateTime updatedAt;
}

```

#### 2.2 MyBatis Mapper `UserWalletMapper.java`

这里使用注解方式（你也可以用 XML），更简洁。包含 PostgreSQL 特有的 `ON CONFLICT` 语法用于充值。

```java
package com.example.ocr.mapper;

import com.example.ocr.entity.UserWallet;
import org.apache.ibatis.annotations.*;

@Mapper
public interface UserWalletMapper {

    @Select("SELECT * FROM user_wallet WHERE app_id = #{appId}")
    UserWallet selectByAppId(@Param("appId") String appId);

    // 核心异步同步方法：只增加已使用次数
    @Update("UPDATE user_wallet SET used_count = used_count + #{cost}, updated_at = NOW() WHERE app_id = #{appId}")
    int incrementUsedCount(@Param("appId") String appId, @Param("cost") int cost);

    // 充值/初始化方法 (PostgreSQL Upsert 写法)
    @Insert("""
        INSERT INTO user_wallet (app_id, total_purchased, used_count)
        VALUES (#{appId}, #{amount}, 0)
        ON CONFLICT (app_id) 
        DO UPDATE SET 
            total_purchased = user_wallet.total_purchased + EXCLUDED.total_purchased,
            updated_at = NOW()
    """)
    void recharge(@Param("appId") String appId, @Param("amount") int amount);
}

```

#### 2.3 异步线程池配置 `AsyncConfig.java`

确保高并发下，数据库同步任务不会阻塞主线程。

```java
package com.example.ocr.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import java.util.concurrent.Executor;

@Configuration
@EnableAsync
public class AsyncConfig {
    @Bean("billingExecutor")
    public Executor billingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(10);
        executor.setMaxPoolSize(50);
        executor.setQueueCapacity(2000);
        executor.setThreadNamePrefix("Async-DB-Sync-");
        executor.initialize();
        return executor;
    }
}

```

#### 2.4 核心业务服务 `BillingService.java`

```java
package com.example.ocr.service;

import com.example.ocr.entity.UserWallet;
import com.example.ocr.mapper.UserWalletMapper;
import jakarta.annotation.PostConstruct;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scripting.support.ResourceScriptSource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

@Slf4j
@Service
@RequiredArgsConstructor
public class BillingService {

    private final StringRedisTemplate redisTemplate;
    private final UserWalletMapper userWalletMapper;
    
    private DefaultRedisScript<Long> deductScript;
    private static final String KEY_PREFIX = "wallet:";

    @PostConstruct
    public void init() {
        deductScript = new DefaultRedisScript<>();
        deductScript.setScriptSource(new ResourceScriptSource(new ClassPathResource("scripts/deduct_hash.lua")));
        deductScript.setResultType(Long.class);
    }

    /**
     * 对外暴露的扣费接口
     */
    public boolean deduct(String appId, int cost) {
        String key = KEY_PREFIX + appId;
        
        // 1. 执行 Lua 脚本
        Long result = redisTemplate.execute(deductScript, Collections.singletonList(key), String.valueOf(cost));

        if (result != null && result == 1) {
            // 2. 扣减成功 -> 异步同步 DB
            syncToDb(appId, cost);
            return true;
        } 
        else if (result != null && result == -1) {
            // 3. 缓存未命中 -> 查库预热
            log.info("Redis miss for appId: {}, reloading...", appId);
            if (reloadToRedis(appId)) {
                // 重载成功后，重试一次
                return deduct(appId, cost);
            }
            return false;
        }
        
        // 4. 余额不足
        return false;
    }

    /**
     * 异步：将扣费同步到 Postgres
     */
    @Async("billingExecutor")
    public void syncToDb(String appId, int cost) {
        try {
            userWalletMapper.incrementUsedCount(appId, cost);
        } catch (Exception e) {
            log.error("Failed to sync DB for appId: {}", appId, e);
            // 生产环境建议发送告警
        }
    }

    /**
     * 缓存预热：从 Postgres 加载到 Redis
     */
    private boolean reloadToRedis(String appId) {
        UserWallet wallet = userWalletMapper.selectByAppId(appId);
        if (wallet == null) return false;

        String key = KEY_PREFIX + appId;
        Map<String, String> hash = new HashMap<>();
        hash.put("total", String.valueOf(wallet.getTotalPurchased()));
        hash.put("used", String.valueOf(wallet.getUsedCount()));

        redisTemplate.opsForHash().putAll(key, hash);
        redisTemplate.expire(key, 24, TimeUnit.HOURS);
        return true;
    }

    /**
     * 充值接口
     */
    @Transactional
    public void recharge(String appId, int amount) {
        // 1. 先写 DB (保证数据持久化)
        userWalletMapper.recharge(appId, amount);
        
        // 2. 更新 Redis (如果存在)
        String key = KEY_PREFIX + appId;
        if (Boolean.TRUE.equals(redisTemplate.hasKey(key))) {
            redisTemplate.opsForHash().increment(key, "total", amount);
        }
        // 如果 Redis key 不存在，不做处理，下次 deduct 时会自动 reload
    }
}

```

#### 2.5 Controller 层 `OcrController.java`

```java
package com.example.ocr.controller;

import com.example.ocr.service.BillingService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/ocr")
@RequiredArgsConstructor
public class OcrController {

    private final BillingService billingService;

    // 模拟的 OCR 业务请求体
    record OcrRequest(String imageBase64) {}

    @PostMapping("/recognize")
    public ResponseEntity<?> recognize(@RequestHeader("X-App-Id") String appId,
                                       @RequestBody OcrRequest request) {
        
        int cost = 1; // 假设单次调用消耗 1 点

        // 1. 先扣费 (高性能 Lua 校验)
        boolean success = billingService.deduct(appId, cost);

        if (!success) {
            return ResponseEntity.status(402).body("Insufficient balance (余额不足)");
        }

        // 2. 执行核心业务
        try {
            // 模拟 OCR 耗时操作
            // String result = ocrEngine.process(request.imageBase64());
            String result = "OCR Result: Hello World"; 
            
            return ResponseEntity.ok(result);
        } catch (Exception e) {
            // 3. (可选) 如果服务报错，这笔钱可以退回吗？
            // 建议：对于高并发系统，偶尔的失败不建议立刻回滚 DB，
            // 可以在 Redis 里补回次数，或者记日志后续人工补偿。
            return ResponseEntity.internalServerError().body("Service Error");
        }
    }
    
    // 模拟充值接口 (方便你测试)
    @PostMapping("/recharge")
    public ResponseEntity<?> recharge(@RequestParam String appId, @RequestParam int amount) {
        billingService.recharge(appId, amount);
        return ResponseEntity.ok("Recharge success");
    }
}

```

### 3. 如何测试使用？

1. **启动项目**：确保 PostgreSQL 和 Redis 正在运行，且 `application.properties` 配置正确。
2. **调用充值接口** (初始化数据)：
* POST `http://localhost:8080/api/ocr/recharge?appId=test_user&amount=10`
* 此时查看数据库：`total_purchased`=10, `used_count`=0。
* 查看 Redis：可能为空（懒加载）。


3. **调用 OCR 接口** (模拟消费)：
* POST `http://localhost:8080/api/ocr/recognize`
* Header: `X-App-Id: test_user`
* Body: `{ "imageBase64": "..." }`


4. **观察结果**：
* 第一次调用：Redis 发现没数据 -> 查 DB -> 载入 Redis -> 扣费成功。
* DB 里的 `used_count` 会异步变为 1。
* 连续调用 10 次后，第 11 次会返回 402 余额不足。



这套代码已经完全适配了你要求的 **MyBatis + PostgreSQL + Redis Lua** 技术栈，且具备生产级的高并发处理能力。
